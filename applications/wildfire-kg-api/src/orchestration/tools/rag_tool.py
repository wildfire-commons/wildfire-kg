from typing import Dict, List, Any, Optional
import logging
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import os
from datetime import datetime

# Import Tavily for web search (you can replace this with any search API)
from tavily import TavilyClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGQueryInput(BaseModel):
    """Input for the RAG query tool."""

    query: str = Field(description="The query to search for in external sources")


class RAGTool(BaseTool):
    """Tool for retrieving information using RAG from external sources."""

    name = "rag_query"
    description = """
    Use this tool to search for information from external sources like the web.
    This is useful when you need up-to-date information that might not be in the knowledge graph,
    such as recent wildfire events, weather conditions, or general information about wildfire management.
    """
    args_schema = RAGQueryInput

    def __init__(self, tavily_api_key: Optional[str] = None):
        """Initialize the RAG tool."""
        super().__init__()
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        if self.tavily_api_key:
            self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
        else:
            logger.warning(
                "No Tavily API key provided. Web search functionality will be limited."
            )
            self.tavily_client = None

    def _run(self, query: str) -> Dict[str, Any]:
        """Run the tool."""
        start_time = datetime.now()
        logger.info(f"Performing RAG query: {query}")

        try:
            documents = []

            # If Tavily client is available, use it for web search
            if self.tavily_client:
                search_result = self.tavily_client.search(
                    query=query,
                    search_depth="advanced",
                    include_domains=[
                        "nps.gov",
                        "fire.ca.gov",
                        "weather.gov",
                    ],  # Relevant domains for wildfire info
                    max_results=5,
                )

                # Format the results
                for result in search_result.get("results", []):
                    documents.append(
                        {
                            "content": result.get("content", ""),
                            "source": result.get("url", ""),
                            "title": result.get("title", ""),
                            "score": result.get("score", 0.0),
                        }
                    )
            else:
                # Mock implementation if no Tavily API key is available
                documents = [
                    {
                        "content": "Wildfires are unplanned fires that burn in natural areas like forests, grasslands or prairies. These dangerous fires spread quickly and can devastate not only wildlife and natural areas, but also communities.",
                        "source": "https://www.ready.gov/wildfires",
                        "title": "Wildfires | Ready.gov",
                        "score": 0.95,
                    },
                    {
                        "content": "The National Weather Service issues Red Flag Warnings & Fire Weather Watches to alert fire departments of the onset, or possible onset, of critical weather and dry conditions that could lead to rapid or dramatic increases in wildfire activity.",
                        "source": "https://www.weather.gov/safety/wildfire",
                        "title": "Wildfire Safety | National Weather Service",
                        "score": 0.85,
                    },
                ]

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return {
                "query": query,
                "documents": documents,
                "source": "web_search",
                "execution_time": execution_time,
            }

        except Exception as e:
            logger.error(f"Error performing RAG query: {str(e)}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "documents": [],
                "source": "web_search",
                "execution_time": 0.0,
            }

    async def _arun(self, query: str) -> Dict[str, Any]:
        """Run the tool asynchronously."""
        # For simplicity, we'll just call the synchronous version
        return self._run(query)
