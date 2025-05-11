"""
Web Search tool using LangChain's tool decorator.
"""

from typing import Dict, List, Any
import logging
from langchain_core.tools import tool
import os
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from wildfire_kg_api.orchestration.prompts import get_prompt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def web_search(query: str) -> str:
    """
    Search the web for information about wildfires and related topics.
    This tool is useful when you need up-to-date information that might not be in the knowledge graph,
    such as recent wildfire events, current conditions, or general information about wildfire management.

    Parameters:
        query: The search query related to wildfires or environmental topics

    Returns:
        A string with summarized information from search results
    """
    logger.info(f"Performing web search for: {query}")

    try:
        # Initialize Tavily client
        tavily_api_key = os.getenv("TAVILY_API_KEY")

        if not tavily_api_key:
            logger.warning("No Tavily API key provided. Using mock search results.")
            return _get_mock_search_results(query)

        tavily_client = TavilyClient(api_key=tavily_api_key)

        # Perform the search
        search_result = tavily_client.search(
            query=query,
            search_depth="basic",  # Use basic depth to get faster, smaller results
            include_domains=[
                "nps.gov",
                "fire.ca.gov",
                "weather.gov",
                "ready.gov",
                "epa.gov",
                "usda.gov",
                "doi.gov",
            ],  # Relevant domains for wildfire info
            max_results=3,  # Limit to fewer results
        )

        # Format the results
        documents = []
        for result in search_result.get("results", []):
            # Truncate long document content
            content = result.get("content", "")
            if len(content) > 1500:
                content = content[:1500] + "... [Content truncated]"

            documents.append(
                {
                    "content": content,
                    "source": result.get("url", ""),
                    "title": result.get("title", ""),
                    "score": result.get("score", 0.0),
                }
            )

        # Summarize the search results
        return _summarize_search_results(documents, query)

    except Exception as e:
        logger.error(f"Error in web search: {str(e)}", exc_info=True)
        return f"I encountered an error while searching the web: {str(e)}. I'll try to provide information based on what I already know about wildfires instead."


def _summarize_search_results(documents: List[Dict[str, Any]], query: str) -> str:
    """Summarize search results using an LLM or return formatted results directly."""
    if not documents:
        return "I couldn't find any relevant information on the web for this query."

    try:
        # Get the web search prompt from registry
        web_search_prompt = get_prompt("tools.web_search.web_search_prompt")

        if web_search_prompt and os.getenv("OPENAI_API_KEY"):
            # Initialize the LLM
            chat_model = ChatOpenAI(
                temperature=0.5,
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-4o-mini",
            )

            # Format documents for the prompt
            formatted_docs = _format_documents(documents)

            # Generate a summary
            response = chat_model.invoke(
                web_search_prompt.format(context=formatted_docs, question=query)
            )

            # Add sources to the response
            sources = "\n\nSources:"
            for i, doc in enumerate(documents, 1):
                sources += f"\n{i}. {doc.get('title', 'Untitled')} - {doc.get('source', 'No URL')}"

            return f"{response.content}{sources}"
        else:
            # Fall back to simple formatting if no LLM available
            return _format_simple_response(documents)

    except Exception as e:
        logger.error(f"Error summarizing search results: {str(e)}", exc_info=True)
        # Fall back to simple formatting
        return _format_simple_response(documents)


def _format_documents(docs: List[Dict]) -> str:
    """Format a list of documents into a single string for the LLM."""
    formatted_docs = ""
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "No title")
        content = doc.get("content", "No content")
        url = doc.get("source", "No source")

        formatted_docs += (
            f"[Document {i}]\nTitle: {title}\nSource: {url}\nContent: {content}\n\n"
        )

    return formatted_docs


def _format_simple_response(documents: List[Dict[str, Any]]) -> str:
    """Format documents into a simple readable response without using an LLM."""
    response = "Here's what I found on the web:\n\n"

    for i, doc in enumerate(documents, 1):
        title = doc.get("title", "Untitled")
        content = doc.get("content", "No content available")
        source = doc.get("source", "No source available")

        # Truncate content if it's too long
        if len(content) > 300:
            content = content[:300] + "..."

        response += f"Source {i}: {title}\n"
        response += f"{content}\n"
        response += f"URL: {source}\n\n"

    return response


def _get_mock_search_results(query: str) -> str:
    """Return mock search results when no API key is available."""
    mock_documents = [
        {
            "content": "Wildfires are unplanned fires that burn in natural areas like forests, grasslands or prairies. These dangerous fires spread quickly and can devastate not only wildlife and natural areas, but also communities.",
            "source": "https://www.ready.gov/wildfires",
            "title": "Wildfires | Ready.gov",
        },
        {
            "content": "The National Weather Service issues Red Flag Warnings & Fire Weather Watches to alert fire departments of the onset, or possible onset, of critical weather and dry conditions that could lead to rapid or dramatic increases in wildfire activity.",
            "source": "https://www.weather.gov/safety/wildfire",
            "title": "Wildfire Safety | National Weather Service",
        },
    ]

    return _format_simple_response(mock_documents)
