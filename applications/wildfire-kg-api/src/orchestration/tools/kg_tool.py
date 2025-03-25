from typing import Dict, List, Any, Optional, Type
import logging
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import os
from datetime import datetime
from langchain_community.graphs import OntotextGraphDBGraph
from langchain_community.chains.graph_qa.ontotext_graphdb import OntotextGraphDBQAChain
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
            query_endpoint = (
                f"{self.graphdb_url}/repositories/{self.graphdb_repository}"
            )
            logger.info(f"Connecting to GraphDB endpoint: {query_endpoint}")

            # Initialize the GraphDB graph with minimal schema query
            self.graph = OntotextGraphDBGraph(
                query_endpoint=query_endpoint,
                # Only fetch essential schema information with strict limits
                query_ontology="""
                    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                    
                    CONSTRUCT {
                        ?s ?p ?o .
                    }
                    WHERE {
                        VALUES ?p {
                            rdf:type
                            wifire:hasTreeShrubMetrics
                            wifire:hasVegetationMetrics
                            wifire:hasFireBehaviorMetrics
                        }
                        ?s ?p ?o .
                    }
                    LIMIT 100
                """,
            )

            # Get prompt templates from the registry
            kg_prompt_template = get_prompt("tools.kg.kg_prompt")
            if not kg_prompt_template:
                logger.warning(
                    "KG prompt not found in registry. Using fallback from original tools.kg_prompt"
                )
                kg_prompt_template = get_prompt("tools.kg_prompt")

            # If still not found, use default prompt
            if not kg_prompt_template:
                logger.warning(
                    "Still no KG prompt found. Using default hardcoded prompt."
                )
                kg_prompt_template = PromptTemplate.from_template(
                    """You are a knowledgeable assistant that helps query a wildfire knowledge graph.
                Focus on finding and returning metrics using these relationships:
                - wifire:hasTreeShrubMetrics
                - wifire:hasVegetationMetrics
                - wifire:hasFireBehaviorMetrics

                Human: {question}
                Assistant: Let me help you query the wildfire knowledge graph.

                {context}

                Based on the knowledge graph data:"""
                )

            # Get SPARQL generation prompt
            sparql_prompt_template = get_prompt("tools.kg.sparql_generation_prompt")
            if not sparql_prompt_template and kg_prompt_template:
                logger.warning(
                    "SPARQL generation prompt not found. Using standard prompt."
                )

            # Initialize the QA chain with templates
            self.qa_chain = OntotextGraphDBQAChain.from_llm(
                ChatOpenAI(
                    temperature=0,
                    api_key=self.openai_api_key,
                    model="gpt-3.5-turbo-0125",
                    max_tokens=1000,
                ),
                graph=self.graph,
                verbose=True,
                return_intermediate_steps=True,
                chain_type="stuff",
                max_tokens_limit=1000,  # Reduced from 2000
                allow_dangerous_requests=True,
                prompt_template=(
                    kg_prompt_template.template
                    if hasattr(kg_prompt_template, "template")
                    else kg_prompt_template
                ),
            )

            logger.info(
                f"Successfully initialized GraphDB connection to {query_endpoint}"
            )
        except Exception as e:
            logger.error(
                f"Error initializing GraphDB connection: {str(e)}", exc_info=True
            )
            raise

    def _get_metric_relationships(self) -> Dict[str, str]:
        """Define the metric relationships and their corresponding properties."""
        return {
            "TreeShrubMetrics": {
                "relationship": "wifire:hasTreeShrubMetrics",
                "properties": [
                    "TreesN",
                    "ShrubsN",
                    "MeanSA",
                    "shrubArea",
                    "scaledShrubArea",
                    "CBH",
                    "MeanSH",
                    "MeanTH",
                    "LF_CBD",
                ],
            },
            "VegetationMetrics": {
                "relationship": "wifire:hasVegetationMetrics",
                "properties": ["NDVI", "EVI", "LAI", "FPAR", "GPP"],
            },
            "FireBehaviorMetrics": {
                "relationship": "wifire:hasFireBehaviorMetrics",
                "properties": ["ROS", "FLI", "FL", "CBD", "CBH"],
            },
        }

    def _fetch_related_metrics(
        self, entity_uri: str, metric_type: str
    ) -> Dict[str, Any]:
        """Fetch metrics related to an entity through a specific relationship."""
        try:
            metric_info = self._get_metric_relationships().get(metric_type, {})
            if not metric_info:
                logger.warning(f"Unknown metric type: {metric_type}")
                return {}

            # Construct SPARQL query to get metrics directly
            metric_query = f"""
                PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                
                SELECT ?metric ?value ?datatype
                FROM <http://wifire.ucsd.edu/plot_metrics>
                WHERE {{
                    <{entity_uri}> wifire:hasTreeShrubMetrics ?metrics .
                    ?metrics ?metric ?value .
                    BIND(DATATYPE(?value) as ?datatype)
                    FILTER(?metric IN (
                        wifire:MDBH,
                        wifire:MLAI,
                        wifire:MaxSD,
                        wifire:MaxSH,
                        wifire:MaxTH,
                        wifire:MeanSA,
                        wifire:MinSD,
                        wifire:SDHT,
                        wifire:SDSD,
                        wifire:SDSHT,
                        wifire:ShrubsN,
                        wifire:TreesN,
                        wifire:plotName,
                        wifire:scaledShrubArea,
                        wifire:shrubArea
                    ))
                }}
                ORDER BY ?metric
            """

            logger.info(f"Fetching {metric_type} metrics for {entity_uri}")
            result = self.graph.query(metric_query)

            # Process and structure the results to match the format
            processed_metrics = []
            for binding in result.get("bindings", []):
                metric_name = binding.get("metric", {}).get("value", "").split("#")[-1]
                value = binding.get("value", {}).get("value")
                datatype = binding.get("datatype", {}).get("value", "")

                # Format the value based on datatype
                if "integer" in datatype:
                    typed_value = f'"{value}"^^xsd:integer'
                elif "float" in datatype:
                    typed_value = f'"{value}"^^xsd:float'
                else:
                    typed_value = f'"{value}"'

                processed_metrics.append(
                    {
                        "subject": entity_uri,
                        "predicate": f"wifire:{metric_name}",
                        "object": typed_value,
                        "graph": "http://wifire.ucsd.edu/plot_metrics",
                    }
                )

            return processed_metrics

        except Exception as e:
            logger.error(f"Error fetching related metrics: {str(e)}", exc_info=True)
            return {}

    def _format_metric_summary(self, metrics: List[Dict[str, Any]]) -> str:
        """Format metrics into a readable summary."""
        summary = "\n\nMetrics Found:\n"

        for i, metric in enumerate(metrics, 1):
            summary += f"{i}\n"
            summary += f"{metric['subject']}\n"
            summary += f"{metric['predicate']}\n"
            summary += f"{metric['object']}\n\n"
            summary += f"{metric['graph']}\n"

        return summary

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
        """Run the tool."""
        start_time = datetime.now()

        # Truncate very long queries to prevent context length issues
        if len(query) > 500:
            logger.warning(
                f"Query too long ({len(query)} chars). Truncating to 500 chars."
            )
            query = query[:500] + "... [Query truncated due to length]"

        logger.info(f"Querying knowledge graph with: {query}")

        try:
            result = self.qa_chain.invoke({self.qa_chain.input_key: query})
            answer = result[self.qa_chain.output_key]
            intermediate_steps = result.get("intermediate_steps", {})

            # Check for metric relationships in the query
            sparql_query = intermediate_steps.get("query", "")
            metric_relationships = self._get_metric_relationships()

            found_relationships = [
                metric_type
                for metric_type, info in metric_relationships.items()
                if info["relationship"].lower() in sparql_query.lower()
            ]

            if found_relationships:
                entity_uris = []
                if "results" in intermediate_steps:
                    for binding in intermediate_steps["results"].get("bindings", []):
                        for value in binding.values():
                            if isinstance(value, dict) and value.get("type") == "uri":
                                entity_uris.append(value["value"])

                additional_metrics = []
                for uri in entity_uris:
                    for metric_type in found_relationships:
                        metrics = self._fetch_related_metrics(uri, metric_type)
                        if metrics:
                            additional_metrics.extend(metrics)

                if additional_metrics:
                    intermediate_steps["additional_metrics"] = additional_metrics
                    metric_summary = self._format_metric_summary(additional_metrics)
                    answer = answer + metric_summary

            # Truncate intermediate steps if they exist
            if intermediate_steps:
                # Truncate SPARQL query if too long
                if len(sparql_query) > 1000:
                    logger.warning(
                        f"SPARQL query is very long ({len(sparql_query)} chars). Truncating to 1000 chars."
                    )
                    intermediate_steps["query"] = (
                        sparql_query[:1000] + "... [Query truncated]"
                    )

                # Truncate any other intermediate results
                for key, value in intermediate_steps.items():
                    if isinstance(value, str) and len(value) > 1000:
                        logger.warning(
                            f"Intermediate step {key} is very long ({len(value)} chars). Truncating."
                        )
                        intermediate_steps[key] = (
                            value[:1000] + "... [Content truncated]"
                        )

            # Truncate very long answers
            if answer and len(answer) > 1000:
                logger.warning(
                    f"Answer is very long ({len(answer)} chars). Truncating to 1000 chars."
                )
                answer = answer[:1000] + "... [Answer truncated due to length]"

            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Total execution time: {execution_time:.2f} seconds")

            # Structure the response with truncated content
            return {
                "query": query,
                "answer": answer,
                "sparql_query": sparql_query,
                "context": intermediate_steps.get("context", ""),
                "execution_time": execution_time,
                "intermediate_steps": intermediate_steps,
            }

        except Exception as e:
            logger.error(f"Error querying knowledge graph: {str(e)}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "answer": "I couldn't find information about that in our knowledge graph.",
                "intermediate_steps": {"error": str(e)},
            }

    async def _arun(self, query: str) -> Dict[str, Any]:
        """Run the tool asynchronously."""
        # For simplicity, we'll just call the synchronous version
        return self._run(query)
