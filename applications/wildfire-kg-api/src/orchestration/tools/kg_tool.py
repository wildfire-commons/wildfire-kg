from typing import Dict, List, Any, Optional, Type
import logging
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import os
from datetime import datetime
from langchain_community.graphs import OntotextGraphDBGraph
from langchain.chains import OntotextGraphDBQAChain
from langchain_openai import ChatOpenAI
import tiktoken  # For token counting
from langchain_core.prompts import PromptTemplate

# Import the prompt registry
from ..prompts import get_prompt

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
        self._initialize_graph()

    def _initialize_graph(self):
        """Initialize the GraphDB connection and QA chain."""
        try:
            # Construct the query endpoint URL
            query_endpoint = (
                f"{self.graphdb_url}/repositories/{self.graphdb_repository}"
            )

            logger.info(f"Connecting to GraphDB endpoint: {query_endpoint}")

            # Initialize the GraphDB graph with a minimal query to reduce token counts
            self.graph = OntotextGraphDBGraph(
                query_endpoint=query_endpoint,
                # Very minimal schema query with strict limits
                query_ontology="CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o . FILTER(?p IN (rdf:type, rdfs:label)) } LIMIT 100",
            )

            # Get prompt templates from the registry
            sparql_generation_template = get_prompt("tools.kg_prompt")
            if not sparql_generation_template:
                raise ValueError(
                    "KG prompt not found. Please ensure it exists in the tools directory."
                )

            # Get the QA prompt template from registry
            qa_template = get_prompt("tools.kg_qa_prompt")
            if not qa_template:
                raise ValueError(
                    "KG QA prompt not found. Please ensure it exists in the tools directory."
                )

            # Initialize the QA chain with templates
            self.qa_chain = OntotextGraphDBQAChain.from_llm(
                ChatOpenAI(
                    temperature=0,
                    api_key=self.openai_api_key,
                    model="gpt-4o-mini",
                    max_tokens=500,
                ),
                graph=self.graph,
                verbose=True,  # Enable verbose mode to see SPARQL queries in logs
                allow_dangerous_requests=True,
                return_intermediate_steps=True,
                max_tokens_limit=2000,
                query_prompt=sparql_generation_template,  # Use template from registry
                response_prompt=qa_template,  # Use template from registry
            )

            logger.info(
                f"Successfully initialized GraphDB connection to {query_endpoint}"
            )
        except Exception as e:
            logger.error(
                f"Error initializing GraphDB connection: {str(e)}", exc_info=True
            )
            raise

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text string."""
        try:
            encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(
                f"Error counting tokens: {str(e)}. Using character estimate instead."
            )
            # Fallback to character-based estimation (rough approximation)
            return len(text) // 4

    def _run(self, query: str) -> Dict[str, Any]:
        """Run the tool using the chain directly."""
        start_time = datetime.now()
        logger.info(f"Querying knowledge graph with: {query}")

        try:
            # Use the QA chain directly - it already does all the steps
            result = self.qa_chain.invoke({"query": query})

            # Extract the answer from the result
            answer = result["result"]
            logger.info(f"Generated answer: {answer}")

            # Extract intermediate steps if available
            sparql_query = "No SPARQL query found"
            context = None

            if "intermediate_steps" in result:
                steps = result["intermediate_steps"]
                if isinstance(steps, dict):
                    # Get SPARQL query
                    if "query" in steps:
                        sparql_query = steps["query"]
                        logger.info(f"Generated SPARQL query:\n{sparql_query}")

                    # Get context/results
                    if "context" in steps:
                        context = steps["context"]
                        logger.info(
                            f"Query results (context passed to LLM):\n{context}"
                        )

                    # Get any database responses
                    if "result" in steps:
                        db_result = steps["result"]
                        logger.info(f"Raw database result:\n{db_result}")

            # If context is still None, try to find it elsewhere
            if context is None and hasattr(self.qa_chain, "last_context"):
                context = self.qa_chain.last_context
                logger.info(f"Found context from chain property:\n{context}")

            # Debug: log full result structure for investigation
            logger.info(f"Result keys: {list(result.keys())}")
            if "intermediate_steps" in result:
                logger.info(
                    f"Intermediate steps keys: {list(result['intermediate_steps'].keys()) if isinstance(result['intermediate_steps'], dict) else 'not a dict'}"
                )

            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Total execution time: {execution_time:.2f} seconds")

            # Create response with extracted components
            return {
                "query": query,
                "answer": answer,
                "sparql_query": sparql_query,
                "context": context,
                "execution_time": execution_time,
            }

        except Exception as e:
            logger.error(f"Error querying knowledge graph: {str(e)}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "answer": "I couldn't find information about that in our knowledge graph.",
            }

    async def _arun(self, query: str) -> Dict[str, Any]:
        """Run the tool asynchronously."""
        # For simplicity, we'll just call the synchronous version
        return self._run(query)
