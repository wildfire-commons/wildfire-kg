from typing import Dict, List, Any, Optional, Type
import logging
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import os
from datetime import datetime
import requests
from urllib.parse import quote
from langchain_community.graphs import OntotextGraphDBGraph
from langchain.chains import OntotextGraphDBQAChain
from langchain_openai import ChatOpenAI

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KnowledgeGraphQueryInput(BaseModel):
    """Input for the knowledge graph query tool."""

    query: str = Field(
        description="The natural language query to convert to a SPARQL query"
    )


class KnowledgeGraphTool(BaseTool):
    """Tool for querying the wildfire knowledge graph using GraphDB."""

    name: str = "knowledge_graph_query"
    description: str = """
    Use this tool to query the wildfire knowledge graph with natural language.
    This tool will convert your natural language query into a SPARQL query and execute it against the GraphDB database.
    It's useful for finding specific information we have integrated into the knowledge graph.
    """
    args_schema: Type[KnowledgeGraphQueryInput] = KnowledgeGraphQueryInput

    # Define the fields properly
    graphdb_url: str = Field(
        default_factory=lambda: os.getenv(
            "GRAPHDB_URL", "https://graphdb-dev-wildfire-kg.nrp-nautilus.io/"
        )
    )
    graphdb_repository: str = Field(
        default_factory=lambda: os.getenv("GRAPHDB_REPOSITORY", "wildfire-kg")
    )
    graphdb_username: Optional[str] = Field(
        default_factory=lambda: os.getenv("GRAPHDB_USERNAME")
    )
    graphdb_password: Optional[str] = Field(
        default_factory=lambda: os.getenv("GRAPHDB_PASSWORD")
    )
    openai_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    graph: Optional[OntotextGraphDBGraph] = Field(default=None)
    qa_chain: Optional[OntotextGraphDBQAChain] = Field(default=None)

    def __init__(
        self,
        graphdb_url: Optional[str] = None,
        graphdb_repository: Optional[str] = None,
        graphdb_username: Optional[str] = None,
        graphdb_password: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        **kwargs,
    ):
        """Initialize the knowledge graph tool for GraphDB."""
        # Pass the values to the parent class constructor
        super().__init__(
            graphdb_url=graphdb_url
            or os.getenv("GRAPHDB_URL", "http://localhost:7200"),
            graphdb_repository=graphdb_repository
            or os.getenv("GRAPHDB_REPOSITORY", "wildfire-kg"),
            graphdb_username=graphdb_username or os.getenv("GRAPHDB_USERNAME"),
            graphdb_password=graphdb_password or os.getenv("GRAPHDB_PASSWORD"),
            openai_api_key=openai_api_key or os.getenv("OPENAI_API_KEY"),
            **kwargs,
        )

        # Initialize the GraphDB connection
        self._initialize_graphdb()

    def _initialize_graphdb(self):
        """Initialize the GraphDB connection and QA chain."""
        try:
            # Construct the query endpoint URL
            query_endpoint = (
                f"{self.graphdb_url}/repositories/{self.graphdb_repository}"
            )

            logger.info(f"Connecting to GraphDB endpoint: {query_endpoint}")

            # Initialize the GraphDB graph with the correct parameters
            # Use a more targeted ontology query to reduce token count
            self.graph = OntotextGraphDBGraph(
                query_endpoint=query_endpoint,
                # Limit the schema to only the most essential triples
                query_ontology="CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o . FILTER(?p IN (rdf:type, rdfs:subClassOf, rdfs:label, rdfs:domain, rdfs:range)) } LIMIT 500",
            )

            # Initialize the QA chain with the graph, using a more compact model
            self.qa_chain = OntotextGraphDBQAChain.from_llm(
                ChatOpenAI(
                    temperature=0,
                    api_key=self.openai_api_key,
                    model="gpt-3.5-turbo-0125",  # More efficient model with 16k context
                    max_tokens=1000,  # Limit response length
                ),
                graph=self.graph,
                verbose=False,  # Reduce verbosity
                allow_dangerous_requests=True,
                return_intermediate_steps=False,  # Don't return intermediate steps to save tokens
            )

            logger.info(
                f"Successfully initialized GraphDB connection to {query_endpoint}"
            )
        except Exception as e:
            logger.error(
                f"Error initializing GraphDB connection: {str(e)}", exc_info=True
            )
            raise

    def _run(self, query: str) -> Dict[str, Any]:
        """Run the tool."""
        start_time = datetime.now()

        # Truncate very long queries to prevent context length issues
        if len(query) > 500:
            logger.warning(
                f"Query is very long ({len(query)} chars). Truncating to 500 chars."
            )
            query = query[:500] + "..."

        logger.info(f"Querying knowledge graph with: {query}")

        try:
            # Use the QA chain to process the query
            result = self.qa_chain.invoke({self.qa_chain.input_key: query})

            # Extract the answer from the result
            answer = result[self.qa_chain.output_key]

            # Truncate very long answers to prevent context length issues in subsequent steps
            if answer and len(answer) > 4000:
                logger.warning(
                    f"Answer is very long ({len(answer)} chars). Truncating to 4000 chars."
                )
                answer = answer[:4000] + "... [Answer truncated due to length]"

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            # Structure the response to be more compact
            return {
                "query": query,
                "answer": answer,
                "execution_time": execution_time,
            }

        except Exception as e:
            logger.error(f"Error querying knowledge graph: {str(e)}", exc_info=True)
            # Return a compact error response
            return {
                "query": query,
                "error": str(e),
                "answer": "I couldn't find information about that in our knowledge graph.",
            }

    async def _arun(self, query: str) -> Dict[str, Any]:
        """Run the tool asynchronously."""
        # For simplicity, we'll just call the synchronous version
        return self._run(query)
