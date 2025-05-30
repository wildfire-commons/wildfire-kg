"""
Web Search tool using LangChain's DuckDuckGo Search integration.
"""

from langchain_core.tools import BaseTool
from langchain_community.tools import DuckDuckGoSearchResults

from wildfire_kg_api.orchestration.logger import get_logger

# Initialize logger
logger = get_logger("tools.web_search")


def web_search() -> BaseTool:
    """
    Instantiates and returns a DuckDuckGoSearchResults tool instance.

    The tool is configured to be named 'web_search' for consistent agent interaction.
    """
    logger.debug(
        "Initializing DuckDuckGo Search with default string output and 3 results limit"
    )
    # Create DuckDuckGo search instance
    # The name is critical for the agent to identify this tool correctly.
    # The description helps the agent decide when to use this tool.
    tool = DuckDuckGoSearchResults(
        name="web_search",
        description="A search engine. Useful for when you need to answer questions about current events, general knowledge, or find up-to-date information.",
        max_results=3,
        # backend="text" # Default, can also be "news", "images", "videos", "maps"
        # output_format="str" # Default is a comma-separated string. "list" or "json" also available.
    )
    # Note: DuckDuckGoSearch does not require an API key for basic use.
    return tool
