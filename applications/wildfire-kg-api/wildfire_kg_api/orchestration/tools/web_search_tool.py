"""
Web Search tool using LangChain's TavilySearch integration.
"""

from langchain_core.tools import BaseTool
import os
from langchain_tavily import TavilySearch

from wildfire_kg_api.orchestration.logger import get_logger

# Initialize logger
logger = get_logger("tools.web_search")


def web_search() -> BaseTool:
    """
    Instantiates and returns a TavilySearch tool instance.
    """
    # Initialize Tavily search
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        logger.warning("No Tavily API key provided.")

    logger.debug("Initializing Tavily search with basic depth and 3 results limit")
    # Create Tavily search instance
    return TavilySearch(
        api_key=tavily_api_key,
        max_results=3,  # Limit to fewer results for focused responses
        search_depth="basic",  # Use basic depth for faster results
    )
