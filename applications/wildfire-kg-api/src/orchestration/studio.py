"""
Script to test the LangGraph workflow with LangGraph Studio.
Run this script to start a local LangGraph Studio server.

Usage:
    python -m src.orchestration.studio

Requirements:
    - langchain-cli
    - langserve
"""

import os
import sys
import logging
from dotenv import load_dotenv
from langchain_cli.langchain_cli import serve_langchain_studio
from langserve import add_routes
from fastapi import FastAPI
from .graph.chat_graph import create_chat_graph, process_user_message
from .state.conversation_state import Message

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def main():
    """Run the LangGraph Studio server."""
    # Check if the required environment variables are set
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is not set")
        sys.exit(1)

    # Create the graph
    graph = create_chat_graph()

    # Create a FastAPI app
    app = FastAPI(
        title="Wildfire Knowledge Graph Chatbot",
        version="0.1.0",
        description="A chatbot that can answer questions about wildfires using a knowledge graph and RAG.",
    )

    # Add routes for the graph
    add_routes(
        app,
        graph,
        path="/api/chat-graph",
    )

    # Add a route for the process_user_message function
    add_routes(
        app,
        process_user_message,
        path="/api/chat",
    )

    # Start the LangGraph Studio server
    serve_langchain_studio(app)


if __name__ == "__main__":
    main()
