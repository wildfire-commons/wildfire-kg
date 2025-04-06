"""
Graph factory module for creating and exposing the LangGraph workflow.

This module is separate from the main application to avoid circular dependencies
between the FastAPI app and the LangGraph setup.
"""

import logging
from dotenv import load_dotenv

# Import the graph creation function
from src.orchestration.graph.chat_graph import create_chat_graph

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def get_graph():
    """
    Returns the chat graph for use with LangGraph.

    This function is referenced in langgraph.json and is used by the langgraph CLI
    to run the application.

    Returns:
        The chat graph instance.
    """
    logger.info("Creating chat graph...")
    return create_chat_graph()
