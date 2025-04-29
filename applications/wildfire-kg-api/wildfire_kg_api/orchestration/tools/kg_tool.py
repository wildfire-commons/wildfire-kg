"""
Knowledge Graph tool for ReAct pattern using LangChain's tool decorator.
"""

from typing import Dict, Any, Optional
import logging
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import os
from datetime import datetime
from langchain_community.graphs import OntotextGraphDBGraph
from langchain_community.chains.graph_qa.ontotext_graphdb import OntotextGraphDBQAChain
from langchain_openai import ChatOpenAI
import tiktoken  # For token counting

# Import the prompt registry
from ..prompts import get_prompt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def query_knowledge_graph(query: str) -> str:
    """
    Query the wildfire knowledge graph with natural language questions.
    This tool converts natural language queries into SPARQL queries and executes them against the GraphDB database.
    Use this tool for finding specific information about wildfires, their impacts, characteristics, and related topics
    that have been integrated into our knowledge graph.

    Parameters:
        query: A natural language question about wildfires and related topics

    Returns:
        A string response with information from the knowledge graph
    """
    logger.info(f"Querying knowledge graph with: {query}")

    try:
        # Connection parameters
        graphdb_url = os.getenv(
            "GRAPHDB_URL", "https://graphdb-dev-wildfire-kg.nrp-nautilus.io/"
        )
        graphdb_repository = os.getenv("GRAPHDB_REPOSITORY", "wildfire-kg")
        graphdb_username = os.getenv("GRAPHDB_USERNAME")
        graphdb_password = os.getenv("GRAPHDB_PASSWORD")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        # Initialize GraphDB connection
        query_endpoint = f"{graphdb_url}/repositories/{graphdb_repository}"

        # Path to the local ontology file
        ontology_file_path = "../../knowledge-representation/wildfire_kg_ontology.owl"

        # Initialize the GraphDB graph with local ontology file
        graph = OntotextGraphDBGraph(
            query_endpoint=query_endpoint,
            local_file=ontology_file_path,
            local_file_format="turtle",  # Explicitly specify the format as Turtle
        )

        # Get prompt templates from the registry
        sparql_generation_prompt = get_prompt("tools.kg.sparql_generation_prompt")
        sparql_fix_prompt = get_prompt("tools.kg.sparql_fix_prompt")
        qa_prompt = get_prompt("tools.kg.qa_prompt")

        # Initialize the QA chain with all available prompts
        qa_chain = OntotextGraphDBQAChain.from_llm(
            ChatOpenAI(
                temperature=0,
                api_key=openai_api_key,
                model="gpt-3.5-turbo",
                max_tokens=1000,
            ),
            graph=graph,
            verbose=True,
            return_intermediate_steps=True,
            chain_type="stuff",
            max_tokens_limit=1000,
            allow_dangerous_requests=True,
            sparql_generation_prompt=sparql_generation_prompt,
            sparql_fix_prompt=sparql_fix_prompt,
            qa_prompt=qa_prompt,
            max_fix_retries=3,
        )

        # Execute the query using the QA chain
        result = qa_chain.invoke({qa_chain.input_key: query})
        answer = result[qa_chain.output_key]
        intermediate_steps = result.get("intermediate_steps", {})

        # Get the generated SPARQL query for logging
        sparql_query = intermediate_steps.get("query", "")
        logger.info(f"Generated SPARQL query: {sparql_query[:200]}...")

        # Create a nicely formatted response
        formatted_response = _format_kg_response(answer, query, intermediate_steps)
        return formatted_response

    except Exception as e:
        logger.error(f"Error querying knowledge graph: {str(e)}", exc_info=True)
        return f"I encountered an issue while querying the knowledge graph: {str(e)}"


def _format_kg_response(
    answer: str, query: str, intermediate_steps: Dict[str, Any]
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

        # Add a footer with source information if we have context
        if has_context:
            response += "\n\n(This information comes from the wildfire knowledge graph database.)"

        return response
    except Exception as e:
        logger.error(f"Error formatting KG response: {str(e)}", exc_info=True)
        return answer  # Fall back to just returning the raw answer
