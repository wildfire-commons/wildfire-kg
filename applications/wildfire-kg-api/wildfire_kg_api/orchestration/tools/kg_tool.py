"""
Knowledge Graph tool for ReAct pattern using LangChain's tool decorator.
"""

from typing import Dict, Any
import os
from pathlib import Path
from langchain_core.tools import tool
from langchain_community.graphs import OntotextGraphDBGraph
from langchain_community.chains.graph_qa.ontotext_graphdb import OntotextGraphDBQAChain
from langchain_openai import ChatOpenAI
from langchain_core.runnables.config import RunnableConfig

from wildfire_kg_api.orchestration.prompts import get_prompt
from wildfire_kg_api.orchestration.logger import get_logger
from wildfire_kg_api.orchestration.models import (
    BEST_MODEL_FALLBACK,
    get_llm_params_for_model,
)

# Initialize logger
logger = get_logger("tools.kg")


@tool
def query_knowledge_graph(query: str, config: RunnableConfig) -> str:
    """
    Query the wildfire knowledge graph with natural language questions.
    This tool converts natural language queries into SPARQL queries and executes them against the GraphDB database.
    Use this tool for finding specific information about wildfires, their impacts, characteristics, and related topics
    that have been integrated into our knowledge graph.

    Parameters:
        query: A natural language question about wildfires and related topics
        config: Optional RunnableConfig containing model settings

    Returns:
        A string response with information from the knowledge graph and follow-up suggestions
    """
    logger.info(f"Querying knowledge graph with: {query} and config: {config}")

    try:
        # Get model settings from config or use defaults
        kg_model_name = config["configurable"].get(
            "kg_model_name", BEST_MODEL_FALLBACK["kg_tool"]["model"]
        )

        # Determine temperature for KG tool:
        # 1. From config's "kg_temperature"
        # 2. From BEST_MODEL_FALLBACK for the kg_tool
        # 3. Default from the model itself (via get_default_temperature)
        kg_temperature_config = config["configurable"].get("kg_temperature")
        if kg_temperature_config is None:
            kg_temperature_config = BEST_MODEL_FALLBACK["kg_tool"].get("temperature")
        # kg_temperature_config can be None. get_llm_params_for_model will handle this.

        verbose = config["configurable"].get(
            "verbose", False
        )  # verbose for QA chain, not directly for LLM here

        # Connection parameters
        graphdb_url = os.getenv(
            "GRAPHDB_URL", "https://graphdb-wildfire-kg.nrp-nautilus.io"
        )
        graphdb_repository = os.getenv("GRAPHDB_REPOSITORY", "wildfire-kg-prod")

        # TODO: Ensure graphdb prevents unauthenticated access
        graphdb_username = os.getenv("GRAPHDB_USERNAME")
        graphdb_password = os.getenv("GRAPHDB_PASSWORD")

        # Initialize GraphDB connection
        query_endpoint = f"{graphdb_url}/repositories/{graphdb_repository}"
        logger.debug(f"Using GraphDB endpoint: {query_endpoint}")

        # Path to the local ontology file
        ontology_file_path = os.path.join(
            os.path.dirname(__file__),
            "knowledge-representation",
            "wildfire_kg_ontology.owl",
        )
        logger.debug(f"Using ontology file at: {ontology_file_path}")

        # Initialize the GraphDB graph with local ontology file
        graph = OntotextGraphDBGraph(
            query_endpoint=query_endpoint,
            local_file=ontology_file_path,
            local_file_format="turtle",  # Explicitly specify the format as Turtle
        )
        logger.debug("GraphDB connection initialized successfully")

        # Get prompt templates from the registry
        sparql_generation_prompt = get_prompt("tools.kg.sparql_generation_prompt")
        sparql_fix_prompt = get_prompt("tools.kg.sparql_fix_prompt")
        qa_prompt = get_prompt("tools.kg.qa_prompt")

        # Set up LLM parameters using the helper function
        logger.info(
            f"KG tool using model: {kg_model_name}, requested temperature: {kg_temperature_config}"
        )
        llm_params = get_llm_params_for_model(
            model_name=kg_model_name,
            temperature_override=kg_temperature_config,
            # No direct callbacks, tags, metadata for this specific LLM instance in the chain yet
        )
        logger.info(f"Final LLM params for KG tool QA chain: {llm_params}")

        # Initialize the QA chain with all available prompts
        qa_chain = OntotextGraphDBQAChain.from_llm(
            ChatOpenAI(**llm_params),
            graph=graph,
            verbose=verbose,  # Pass verbose to the chain itself
            return_intermediate_steps=True,
            chain_type="stuff",
            allow_dangerous_requests=True,
            sparql_generation_prompt=sparql_generation_prompt,
            sparql_fix_prompt=sparql_fix_prompt,
            qa_prompt=qa_prompt,
            max_fix_retries=3,
        )
        logger.debug("QA chain initialized successfully")

        # Execute the query using the QA chain
        logger.debug("Executing query through QA chain...")
        result = qa_chain.invoke({qa_chain.input_key: query})
        answer = result[qa_chain.output_key]
        intermediate_steps = result.get("intermediate_steps", {})

        # Get the generated SPARQL query for logging
        sparql_query = intermediate_steps.get("query", "")
        logger.debug(f"Generated SPARQL query: {sparql_query}")

        # Create a nicely formatted response
        formatted_response = _format_kg_response(
            answer, query, intermediate_steps, kg_model_name, kg_temperature_config
        )
        return formatted_response

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
        # Clean up the answer
        if not answer or answer.strip() == "":
            return "I couldn't find relevant information about this in the knowledge graph."

        # Extract context information if available
        context = intermediate_steps.get("context", "")
        has_context = context and len(context.strip()) > 0

        # Create a response with appropriate formatting
        response = f"{answer}"

        # Generate follow-up questions based on the query, answer, and context
        follow_up_questions = _generate_follow_up_questions(
            query, answer, context, model_name, temperature
        )
        if follow_up_questions:
            response += f"\n\nYou might also be interested in:\n{follow_up_questions}"

        # Add a footer with source information if we have context
        if has_context:
            response += "\n\n(This information comes from the wildfire knowledge graph database.)"

        return response
    except Exception as e:
        logger.error(f"Error formatting KG response: {str(e)}", exc_info=True)
        return answer  # Fall back to just returning the raw answer


def _generate_follow_up_questions(
    query: str,
    answer: str,
    context: str,
    model_name: str = None,
    temperature: float = 0.0,
) -> str:
    """Generate follow-up questions based on the query, answer, and context."""
    try:
        # Determine model and temperature for follow-up questions LLM
        # Default to the same model as the KG tool or fallback
        llm_model_name = model_name or BEST_MODEL_FALLBACK["kg_tool"]["model"]

        # For temperature, prioritize the passed `temperature` param (which might be from original KG config),
        # then the model's default. This `temperature` param in _generate_follow_up_questions
        # effectively acts as temperature_override.

        logger.info(
            f"Follow-up questions using model: {llm_model_name}, requested temperature: {temperature}"
        )
        llm_params = get_llm_params_for_model(
            model_name=llm_model_name,
            temperature_override=temperature,  # The `temperature` argument acts as override
        )
        logger.info(f"Final LLM params for follow-up questions: {llm_params}")

        # Use the LLM for consistency
        llm = ChatOpenAI(**llm_params)

        # Construct a prompt to generate follow-up questions
        prompt = f"""
        Based on the following query and answer about fire, vegetation, or fuel data, suggest 1-2 simple follow-up questions that would be relevant and interesting.
        
        The follow-up questions should relate to:
        1. Other metrics or measurements related to the current query
        2. Comparisons with other similar plots or regions
        3. Temporal aspects (changes over time, different seasons)
        4. Causal relationships or correlations
        
        Original Query: {query}
        Answer: {answer}
        Additional Context: {context}
        
        Generate only the questions, no explanations or introductions.
        """

        # Get the follow-up questions from the LLM
        response = llm.invoke(prompt)
        follow_up_text = response.content.strip()

        # Clean up the response to ensure it's just the questions
        follow_up_text = follow_up_text.replace("1. ", "• ")
        follow_up_text = follow_up_text.replace("2. ", "• ")

        return follow_up_text
    except Exception as e:
        logger.error(f"Error generating follow-up questions: {str(e)}", exc_info=True)
        return ""  # Return empty string if there's an error
