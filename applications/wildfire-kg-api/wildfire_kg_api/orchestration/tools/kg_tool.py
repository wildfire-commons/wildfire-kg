"""
Knowledge Graph tool for ReAct pattern using LangChain's tool decorator.
"""

from typing import Dict, Any, Optional
import os
from langchain_core.tools import tool
from langchain_community.graphs import OntotextGraphDBGraph
from langchain_community.chains.graph_qa.ontotext_graphdb import OntotextGraphDBQAChain
from langchain_openai import ChatOpenAI
from langchain_core.runnables.config import RunnableConfig
from langchain.prompts import PromptTemplate
import re
import json # Added for parsing JSON output

from wildfire_kg_api.orchestration.prompts import get_prompt
from wildfire_kg_api.orchestration.logger import get_logger
from wildfire_kg_api.orchestration.models import (
    BEST_MODEL_FALLBACK,
    get_llm_params_for_model,
)

# Initialize logger
logger = get_logger("tools.kg")

def _parse_json_classification_output(llm_output: str) -> Dict[str, str]:
    """Parse the JSON output of the query classification LLM."""
    try:
        # Remove potential markdown ```json ... ```
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:]
            if llm_output.endswith("```"):
                llm_output = llm_output[:-3]
        
        data = json.loads(llm_output.strip())
        return {
            "query_type": data.get("query_type", "other"),
            "confidence": data.get("confidence", "low"),
            "reasoning": data.get("reasoning", "N/A"),
        }
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from classification LLM: {str(e)}\nOutput was: {llm_output}", exc_info=True)
        return {
            "query_type": "other",
            "confidence": "low",
            "reasoning": f"JSON parsing failed: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Unexpected error parsing classification output: {str(e)}\nOutput was: {llm_output}", exc_info=True)
        return {
            "query_type": "other",
            "confidence": "low",
            "reasoning": f"Unexpected parsing error: {str(e)}",
        }

def _parse_context_lookup_output(llm_output: str, query_type_for_parsing: str) -> Dict[str, str]:
    """
    Parse the output of the query context lookup LLM.
    The LLM is expected to return a block of text corresponding to the query_type.
    This function extracts context, example_query, and example_sparql from that block.
    """
    try:
        # Normalize query_type for block searching (e.g., "slope_question" -> "SLOPE_QUESTION")
        # block_type_marker = query_type_for_parsing.upper()
        # More robust: directly use the yaml structure for keys
        # The prompt for context lookup should ideally instruct the LLM to return a JSON.
        # However, following user's current prompt design for query_context_prompt.yaml,
        # which implies the LLM selects a block. We will try to parse based on that.

        # Attempt to find the specific block first. The user's context prompt is complex.
        # It has sections like "slope_question:", "fuel_model_question:", etc.
        # The LLM is supposed to effectively perform a lookup in its own prompt.
        # The most robust way if the LLM *doesn't* return JSON is to parse based on the structure
        # of the content *within* those blocks.

        context_match = re.search(r"context:((?:.|\n)*?)example_query:", llm_output, re.IGNORECASE)
        example_query_match = re.search(r"example_query:((?:.|\n)*?)example_sparql:", llm_output, re.IGNORECASE)
        example_sparql_match = re.search(r"example_sparql:((?:.|\n)*)", llm_output, re.IGNORECASE)

        # A simpler assumption: the LLM returns *only* the content of the matched block.
        # If so, the regexes above should work on that isolated block.
        # If the LLM returns the *entire* context prompt content with a marker, this parsing is harder.
        # The user's prompt for query_context_prompt is:
        # "Based on the query type "{query_type}", provide context and example for generating SPARQL queries."
        # This implies the LLM should output the relevant section.

        extracted_context = context_match.group(1).strip() if context_match else "Context not found or parsing error."
        extracted_example_query = example_query_match.group(1).strip() if example_query_match else "Example query not found."
        
        # For SPARQL, remove the pipe and leading/trailing spaces from multiline YAML if present
        raw_sparql = example_sparql_match.group(1).strip() if example_sparql_match else "# Example SPARQL not found."
        if raw_sparql.startswith("|"):
            raw_sparql = raw_sparql[1:].strip()
        # Remove leading/trailing ```sparql and ``` if present by mistake
        if raw_sparql.startswith("```sparql"):
            raw_sparql = raw_sparql[9:]
            if raw_sparql.endswith("```"):
                raw_sparql = raw_sparql[:-3]
        elif raw_sparql.startswith("```"): # if only ```
             raw_sparql = raw_sparql[3:]
             if raw_sparql.endswith("```"):
                raw_sparql = raw_sparql[:-3]
        raw_sparql = raw_sparql.strip()


        return {
            "query_type_context": extracted_context,
            "example_nl_query": extracted_example_query,
            "example_sparql_query_with_double_braces": raw_sparql,
        }
    except Exception as e:
        logger.error(f"Error parsing context lookup LLM output: {str(e)}\nOutput was: {llm_output}", exc_info=True)
        return {
            "query_type_context": "Error parsing context from LLM.",
            "example_nl_query": "Error parsing example NL query.",
            "example_sparql_query_with_double_braces": "# Error parsing example SPARQL.",
        }

@tool
def query_knowledge_graph(query: str, config: RunnableConfig) -> str:
    """
    Query the wildfire knowledge graph with natural language questions using a two-step classification
    and context retrieval process before generating SPARQL.
    """
    logger.info(f"Querying knowledge graph with: '{query}' and config: {config}")

    try:
        kg_model_name = config["configurable"].get("kg_model_name", BEST_MODEL_FALLBACK["kg_tool"]["model"])
        kg_temperature_config = config["configurable"].get("kg_temperature")
        if kg_temperature_config is None:
            kg_temperature_config = BEST_MODEL_FALLBACK["kg_tool"].get("temperature")
        verbose = config["configurable"].get("verbose", False)

        # --- Step 1: Query Classification ---
        logger.debug("Starting Step 1: Query Classification")
        classification_llm_params = get_llm_params_for_model(
            model_name=kg_model_name, temperature_override=kg_temperature_config
        )
        classification_llm = ChatOpenAI(**classification_llm_params)
        classification_prompt_obj = get_prompt("tools.kg.query_classification_prompt")

        classification_data = {
            "query_type": "other", "confidence": "low", "reasoning": "Classification prompt not found."
        }

        if classification_prompt_obj:
            try:
                formatted_prompt = classification_prompt_obj.format(query=query)
                response_content = classification_llm.invoke(formatted_prompt).content
                classification_data = _parse_json_classification_output(response_content)
                logger.info(f"Step 1 Classification successful: {classification_data}")
            except Exception as e:
                logger.error(f"Error during Step 1 (Query Classification): {str(e)}", exc_info=True)
                classification_data["reasoning"] = f"Classification failed: {str(e)}"
        else:
            logger.warning("Query classification prompt 'tools.kg.query_classification_prompt' not found.")
        
        query_type = classification_data["query_type"]
        confidence = classification_data["confidence"]
        reasoning = classification_data["reasoning"]

        # --- Step 2: Query Context Retrieval ---
        logger.debug(f"Starting Step 2: Query Context Retrieval for query_type='{query_type}'")
        context_llm_params = get_llm_params_for_model( # Can use same/diff model
            model_name=kg_model_name, temperature_override=kg_temperature_config 
        )
        context_llm = ChatOpenAI(**context_llm_params)
        context_prompt_obj = get_prompt("tools.kg.query_context_prompt")

        context_details = {
            "query_type_context": "Context prompt not found or processing failed.",
            "example_nl_query": "N/A",
            "example_sparql_query_with_double_braces": "# N/A"
        }

        if context_prompt_obj:
            try:
                # The context_prompt_obj itself is the large lookup table.
                # The LLM's job is to effectively select the relevant part based on query_type.
                formatted_context_prompt = context_prompt_obj.format(
                    query_type=query_type, confidence=confidence, reasoning=reasoning
                )
                # The LLM should be instructed by query_context_prompt.yaml to return the relevant block.
                context_response_content = context_llm.invoke(formatted_context_prompt).content
                context_details = _parse_context_lookup_output(context_response_content, query_type)
                logger.info(f"Step 2 Context Retrieval successful for query_type='{query_type}'. Context found: {bool(context_details['query_type_context'] != 'Context not found or parsing error.')}")

            except Exception as e:
                logger.error(f"Error during Step 2 (Query Context Retrieval): {str(e)}", exc_info=True)
                context_details["query_type_context"] = f"Context retrieval failed: {str(e)}"
        else:
            logger.warning("Query context prompt 'tools.kg.query_context_prompt' not found.")

        # --- Step 3: SPARQL Generation ---
        logger.debug("Starting Step 3: SPARQL Generation")
        graphdb_url = os.getenv("GRAPHDB_URL", "https://graphdb-dev-wildfire-kg.nrp-nautilus.io")
        graphdb_repository = os.getenv("GRAPHDB_REPOSITORY", "wildfire-kg")
        ontology_file_path = "../../knowledge-representation/wildfire_kg_ontology.owl"
        query_endpoint = f"{graphdb_url}/repositories/{graphdb_repository}"

        graph = OntotextGraphDBGraph(
            query_endpoint=query_endpoint, local_file=ontology_file_path, local_file_format="turtle"
        )

        raw_sparql_generation_prompt_obj = get_prompt("tools.kg.sparql_generation_prompt")
        sparql_fix_prompt_obj = get_prompt("tools.kg.sparql_fix_prompt")
        qa_prompt_obj = get_prompt("tools.kg.qa_prompt")

        if not raw_sparql_generation_prompt_obj:
            logger.error("SPARQL generation prompt 'tools.kg.sparql_generation_prompt' not found.")
            return "Error: SPARQL generation prompt is missing."
        
        if qa_prompt_obj:
            logger.debug(f"QA prompt loaded. Inferred input variables: {qa_prompt_obj.input_variables}")
        else:
            logger.error("QA prompt 'tools.kg.qa_prompt' not found.") # Critical for the chain
            return "Error: QA prompt for result summarization is missing."

        if sparql_fix_prompt_obj:
            logger.debug(f"SPARQL fix prompt loaded. Inferred input variables: {sparql_fix_prompt_obj.input_variables}")
        else:
            logger.warning("SPARQL fix prompt 'tools.kg.sparql_fix_prompt' not found. Chain will operate without SPARQL fixing.")

        # Use PromptTemplate.from_template for robust input variable inference
        partial_vars_map = {
            "query_type_context": context_details["query_type_context"],
            "example_nl_query": context_details["example_nl_query"],
            "example_sparql_query_with_double_braces": context_details["example_sparql_query_with_double_braces"],
        }
        final_sparql_generation_prompt = PromptTemplate.from_template(
            template=raw_sparql_generation_prompt_obj.template,
            partial_variables=partial_vars_map
        )
        # Logging the inferred input variables for debugging
        logger.debug(f"Final SPARQL generation prompt created. Inferred input variables: {final_sparql_generation_prompt.input_variables}")
        
        qa_chain_llm_params = get_llm_params_for_model(
            model_name=kg_model_name, temperature_override=kg_temperature_config
        )
        
        # Comment out QA chain creation and execution
        """
        qa_chain = OntotextGraphDBQAChain.from_llm(
            ChatOpenAI(**qa_chain_llm_params),
            graph=graph,
            verbose=verbose,
            return_intermediate_steps=True,
            chain_type="stuff", 
            allow_dangerous_requests=True,
            sparql_generation_prompt=final_sparql_generation_prompt,
            sparql_fix_prompt=sparql_fix_prompt_obj, # Optional, chain can handle None
            qa_prompt=qa_prompt_obj, # Essential
            max_fix_retries=3,
        )

        logger.debug("Executing query through QA chain...")
        result = qa_chain.invoke({
            "query": query,
            "question": query  # Add both keys with the same value
        })
        answer = result[qa_chain.output_key]
        intermediate_steps = result.get("intermediate_steps", {})
        sparql_query_generated = intermediate_steps.get("query", "")
        logger.info(f"Generated SPARQL query: \n{sparql_query_generated}")
        """
        
        # Generate SPARQL query directly using the LLM
        logger.debug("Generating SPARQL query directly...")
        sparql_llm = ChatOpenAI(**qa_chain_llm_params)
        sparql_response = sparql_llm.invoke(final_sparql_generation_prompt.format(question=query))
        sparql_query_generated = sparql_response.content.strip()
        logger.info(f"Generated SPARQL query: \n{sparql_query_generated}")

        # Execute SPARQL query directly
        try:
            sparql_result = graph.query(sparql_query_generated)
            context = list(sparql_result)  # Convert to list for consistency
        except Exception as e:
            logger.error(f"Error executing SPARQL query: {str(e)}", exc_info=True)
            context = []
            sparql_query_generated = f"Error: {str(e)}"

        # Generate answer using QA prompt directly
        if qa_prompt_obj:
            qa_llm = ChatOpenAI(**qa_chain_llm_params)
            qa_response = qa_llm.invoke(qa_prompt_obj.format(
                context=str(context),
                question=query
            ))
            answer = qa_response.content.strip()
        else:
            answer = "Error: QA prompt not found"

        intermediate_steps = {
            "context": context,
            "query": sparql_query_generated
        }

        # _format_kg_response may need an update if its assumptions changed
        return _format_kg_response(
            answer, query, intermediate_steps, kg_model_name, kg_temperature_config
        )

    except Exception as e:
        logger.error(f"Error querying knowledge graph: {str(e)}", exc_info=True)
        return f"I encountered an issue while querying the knowledge graph: {str(e)}"

def _format_kg_response(
    answer: str,
    query: str,
    intermediate_steps: Dict[str, Any],
    model_name: str = None,
    temperature: float = 0.0,
) -> str:
    """Format the knowledge graph response in a user-friendly manner."""
    try:
        if not answer or answer.strip() == "":
            # Check for errors in intermediate steps if no direct answer
            if "error" in intermediate_steps:
                 return f"I couldn't find relevant information. Error during processing: {intermediate_steps['error']}"
            return "I couldn't find relevant information about this in the knowledge graph."

        context = intermediate_steps.get("context", "") # This context is from GraphDB result
        has_context = context and isinstance(context, list) and len(context) > 0


        response = f"{answer}"

        follow_up_questions = _generate_follow_up_questions(
            query, answer, str(context), model_name, temperature # Pass context as string
        )
        if follow_up_questions:
            response += f"\n\nYou might also be interested in:\n{follow_up_questions}"

        if has_context:
            response += "\n\n(This information comes from the wildfire knowledge graph database.)"
        else:
            # If no direct context from DB, but we got an answer, it might be from LLM processing the (empty) DB result
            response += "\n\n(The answer was generated based on the query against the wildfire knowledge graph.)"


        return response
    except Exception as e:
        logger.error(f"Error formatting KG response: {str(e)}", exc_info=True)
        return answer


def _generate_follow_up_questions(
    query: str,
    answer: str,
    context_str: str, # Changed to context_str to reflect it's a string representation
    model_name: str = None,
    temperature: float = 0.0,
) -> str:
    """Generate follow-up questions based on the query, answer, and context string."""
    try:
        llm_model_name = model_name or BEST_MODEL_FALLBACK["kg_tool"]["model"]
        
        logger.info(
            f"Follow-up questions using model: {llm_model_name}, requested temperature: {temperature}"
        )
        llm_params = get_llm_params_for_model(
            model_name=llm_model_name,
            temperature_override=temperature,
        )
        logger.info(f"Final LLM params for follow-up questions: {llm_params}")

        llm = ChatOpenAI(**llm_params)

        prompt_text = f"""
        Based on the following query and answer about fire, vegetation, or fuel data, suggest 1-2 simple follow-up questions that would be relevant and interesting.
        
        The follow-up questions should relate to:
        1. Other metrics or measurements related to the current query
        2. Comparisons with other similar plots or regions
        3. Temporal aspects (changes over time, different seasons)
        4. Causal relationships or correlations
        
        Original Query: {query}
        Answer: {answer}
        Additional Context from Knowledge Graph: {context_str}
        
        Generate only the questions, no explanations or introductions. Each question should start with a bullet point (e.g., • Question text).
        """

        response = llm.invoke(prompt_text)
        follow_up_text = response.content.strip()

        # Ensure bullet points if not already present by LLM
        lines = [line.strip() for line in follow_up_text.split('\n') if line.strip()]
        formatted_lines = []
        for line in lines:
            if not line.startswith("• ") and not line.startswith("* ") and not line.startswith("- "):
                formatted_lines.append(f"• {line}")
            else:
                formatted_lines.append(line)
        
        return "\n".join(formatted_lines)
    except Exception as e:
        logger.error(f"Error generating follow-up questions: {str(e)}", exc_info=True)
        return ""
