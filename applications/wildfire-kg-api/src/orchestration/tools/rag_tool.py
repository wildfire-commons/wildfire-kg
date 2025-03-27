from typing import Dict, List, Any, Optional, Type
import logging
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import os
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

# Import Tavily for web search (you can replace this with any search API)
from tavily import TavilyClient

# Import the prompt registry
from ..prompts import get_prompt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGQueryInput(BaseModel):
    """Input for the RAG query tool."""

    query: str = Field(description="The query to search for in external sources")


class RAGTool(BaseTool):
    """Tool for retrieving information using RAG from external sources."""

    name: str = "rag_query"
    description: str = """
    Use this tool to search for information from external sources like the web.
    This is useful when you need up-to-date information that might not be in the knowledge graph,
    such as recent wildfire events, weather conditions, or general information about wildfire management.
    """
    args_schema: Type[RAGQueryInput] = RAGQueryInput

    # Define the fields properly
    tavily_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("TAVILY_API_KEY")
    )
    tavily_client: Optional[TavilyClient] = None

    def __init__(self, tavily_api_key: Optional[str] = None, **kwargs):
        """Initialize the RAG tool."""
        # Pass the values to the parent class constructor
        api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        super().__init__(tavily_api_key=api_key, **kwargs)

        # Initialize the Tavily client
        if api_key:
            self.tavily_client = TavilyClient(api_key=api_key)
        else:
            logger.warning(
                "No Tavily API key provided. Web search functionality will be limited."
            )
            self.tavily_client = None

    def _run(self, query: str) -> Dict[str, Any]:
        """Run the tool."""
        start_time = datetime.now()

        # Truncate very long queries to prevent context length issues
        if len(query) > 500:
            logger.warning(
                f"Query is very long ({len(query)} chars). Truncating to 500 chars."
            )
            query = query[:500] + "..."

        logger.info(f"Performing RAG query: {query}")

        try:
            documents = []

            # If Tavily client is available, use it for web search
            if self.tavily_client:
                search_result = self.tavily_client.search(
                    query=query,
                    search_depth="basic",  # Use basic depth to get faster, smaller results
                    include_domains=[
                        "nps.gov",
                        "fire.ca.gov",
                        "weather.gov",
                    ],  # Relevant domains for wildfire info
                    max_results=3,  # Limit to fewer results to reduce token count
                )

                # Format the results
                for result in search_result.get("results", []):
                    # Truncate long document content
                    content = result.get("content", "")
                    if len(content) > 2000:
                        content = (
                            content[:2000] + "... [Content truncated due to length]"
                        )

                    documents.append(
                        {
                            "content": content,
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

            # Limit the total number of documents if there are too many
            if len(documents) > 3:
                logger.warning(
                    f"Limiting from {len(documents)} documents to 3 to reduce token count"
                )
                documents = documents[:3]

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            # Get the RAG prompt
            rag_prompt = get_prompt("tools.rag_prompt")
            if not rag_prompt:
                raise ValueError(
                    "RAG prompt not found. Please ensure it exists in the tools directory."
                )

            # Initialize the LLM
            chat_model = ChatOpenAI(
                temperature=0.5,
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-4o-mini",
            )

            # Use this prompt with your documents
            formatted_docs = self.format_documents(documents)
            answer = chat_model.invoke(
                rag_prompt.format(context=formatted_docs, question=query)
            )

            return {
                "query": query,
                "documents": documents,
                "answer": answer.content,
                "execution_time": execution_time,
            }

        except Exception as e:
            logger.error(f"Error in RAG query: {str(e)}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "documents": [],
                "answer": f"I apologize, but I encountered an error while searching for information: {str(e)}. Please try again with a different query.",
                "execution_time": 0.0,
            }

    async def _arun(self, query: str) -> Dict[str, Any]:
        """Run the tool asynchronously."""
        # For simplicity, we'll just call the synchronous version
        return self._run(query)

    def format_documents(self, docs: List[Dict]) -> str:
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
