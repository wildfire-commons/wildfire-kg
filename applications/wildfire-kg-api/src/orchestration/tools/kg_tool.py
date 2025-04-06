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
from langchain.prompts import ChatPromptTemplate

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
            query_endpoint = f"{self.graphdb_url}/repositories/{self.graphdb_repository}"
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

            # Initialize the QA chain with optimized prompt
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
                prompt_template="""You are a knowledgeable assistant that helps query a wildfire knowledge graph.
                Focus on finding and returning metrics using these relationships:
                - wifire:hasTreeShrubMetrics
                - wifire:hasVegetationMetrics
                - wifire:hasFireBehaviorMetrics

                Human: {question}
                Assistant: Let me help you query the wildfire knowledge graph.

                {context}

                Based on the knowledge graph data:"""
            )

            logger.info(f"Successfully initialized GraphDB connection to {query_endpoint}")
        except Exception as e:
            logger.error(f"Error initializing GraphDB connection: {str(e)}", exc_info=True)
            raise

    def _get_metric_relationships(self) -> Dict[str, str]:
        """Define the metric relationships and their corresponding properties."""
        return {
            'TreeShrubMetrics': {
                'relationship': 'wifire:hasTreeShrubMetrics',
                'properties': [
                    'TreesN', 'ShrubsN', 'MeanSA', 'shrubArea', 'scaledShrubArea',
                    'CBH', 'MeanSH', 'MeanTH', 'LF_CBD'
                ]
            },
            'FireBehaviorMetrics': {
                'relationship': 'wifire:hasFireBehaviorMetrics',
                'properties': [
                    'LF_FBFM13',  # Landfire Fuel Model 13
                    'LF_FBFM40',  # Landfire Fuel Model 40
                    'LF_CBD',     # Canopy Bulk Density
                    'LF_CBH',     # Canopy Base Height
                    'LF_FDist'    # Fire Disturbance
                ]
            }
        }

    def _fetch_related_metrics(self, entity_uri: str, metric_type: str) -> Dict[str, Any]:
        """Fetch metrics related to an entity through a specific relationship."""
        try:
            metric_info = self._get_metric_relationships().get(metric_type, {})
            if not metric_info:
                logger.warning(f"Unknown metric type: {metric_type}")
                return {}

            # Define query templates for different metric types
            query_templates = {
                'VegetationMetrics': """
                    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                    
                    SELECT ?property ?value
                    FROM <http://wifire.ucsd.edu/plot_metrics>
                    WHERE {
                        <{entity_uri}> wifire:hasVegetationMetrics ?metrics .
                        ?metrics ?property ?value .
                    }
                    ORDER BY ?property
                """,
                'TreeShrubMetrics': """
                    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                    
                    SELECT ?property ?value
                    FROM <http://wifire.ucsd.edu/plot_metrics>
                    WHERE {
                        <{entity_uri}> wifire:hasTreeShrubMetrics ?metrics .
                        ?metrics ?property ?value .
                    }
                    ORDER BY ?property
                """,
                'FireBehaviorMetrics': """
                    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                    
                    SELECT ?property ?value
                    FROM <http://wifire.ucsd.edu/plot_metrics>
                    WHERE {
                        <{entity_uri}> wifire:hasFireBehaviorMetrics ?metrics .
                        ?metrics ?property ?value .
                    }
                    ORDER BY ?property
                """
            }

            # Get the appropriate query template
            metric_query = query_templates.get(metric_type, "")
            if not metric_query:
                logger.warning(f"No query template for metric type: {metric_type}")
                return {}

            # Format the query with the entity URI
            metric_query = metric_query.format(entity_uri=entity_uri)
            
            logger.info(f"Fetching {metric_type} metrics for {entity_uri}")
            result = self.graph.query(metric_query)
            
            # Process and structure the results
            processed_metrics = []
            for binding in result.get('bindings', []):
                property_name = binding.get('property', {}).get('value', '').split('#')[-1]
                value = binding.get('value', {}).get('value')
                
                processed_metrics.append({
                    'subject': entity_uri,
                    'predicate': f'wifire:{property_name}',
                    'object': value,
                    'graph': 'http://wifire.ucsd.edu/plot_metrics'
                })
            
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

    def _run(self, query: str) -> Dict[str, Any]:
        """Run the tool with recursive reasoning."""
        start_time = datetime.now()
        logger.info(f"Starting recursive KG query: {query}")

        try:
            # Initialize the reasoning chain with structured output
            class ReasoningOutput(BaseModel):
                needs_additional_queries: bool = Field(description="Whether additional queries are needed")
                reasoning: str = Field(description="Explanation of the decision")
                next_query: Optional[str] = Field(description="Next query to execute if needed")
                final_answer: Optional[str] = Field(description="Final synthesized answer")

            reasoning_llm = ChatOpenAI(temperature=0, model="gpt-4-turbo-preview").with_structured_output(ReasoningOutput)
            
            # Initial query
            result = self.qa_chain.invoke({
                self.qa_chain.input_key: """
                When comparing plot metrics, use the date in the plot ID to determine temporal order.
                For example:
                - wifire:plot_CASBC_0001_20240910_1 was measured on 2024-09-10
                - wifire:plot_CASBC_0001_20241116_1 was measured on 2024-11-16
                
                Query: """ + query
            })
            all_results = [result]
            reasoning_chain = []
            
            max_iterations = 2
            iteration = 0
            
            while iteration < max_iterations:
                previous_results = "\n".join([
                    f"Step {i+1}: {r[self.qa_chain.output_key]}"
                    for i, r in enumerate(all_results)
                ])
                
                reasoning = reasoning_llm.invoke(
                    f"""Query: {query}
                    Previous Results: {previous_results}
                    
                    For temporal comparisons of plot metrics:
                    1. Extract dates from plot IDs (format: plot_SITE_PLOT_YYYYMMDD_VERSION)
                    2. Order measurements chronologically
                    3. Compare metrics between timestamps
                    
                    For fuel consumption queries, we need to:
                    1. Get FireBehaviorMetrics (LF_FBFM13, LF_FBFM40) for both plots
                    2. Get TreeShrubMetrics (CBH, TreesN, ShrubsN) for both plots
                    3. Compare the metrics between the two timestamps
                    4. Calculate the consumption based on changes in these metrics
                    
                    Determine if additional queries are needed. Consider:
                    1. Are there related metrics we should look up?
                    2. Do we need to compare values across time periods?
                    3. Should we calculate differences between measurements?
                    4. Are there connected entities we should explore?"""
                )
                
                reasoning_chain.append({
                    "iteration": iteration,
                    "reasoning": reasoning.reasoning,
                    "needs_more_queries": reasoning.needs_additional_queries,
                    "next_query": reasoning.next_query
                })
                
                if not reasoning.needs_additional_queries:
                    break
                    
                if reasoning.next_query:
                    logger.info(f"Executing follow-up query: {reasoning.next_query}")
                    next_result = self.qa_chain.invoke({
                        self.qa_chain.input_key: "Remember to use dates from plot IDs for temporal ordering. " + reasoning.next_query
                    })
                    all_results.append(next_result)
                
                iteration += 1

            final_answer = reasoning_llm.invoke(
                f"""Synthesize a complete answer from these query results:
                {chr(10).join([r[self.qa_chain.output_key] for r in all_results])}
                
                Remember:
                1. Plot IDs contain measurement dates (format: plot_SITE_PLOT_YYYYMMDD_VERSION)
                2. Order and compare metrics chronologically
                3. Calculate changes between timestamps
                
                Focus on:
                1. Changes in fuel models (LF_FBFM13, LF_FBFM40)
                2. Changes in vegetation metrics (CBH, TreesN, ShrubsN)
                3. Calculate and explain the fuel consumption based on these changes"""
            ).final_answer

            execution_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "query": query,
                "answer": final_answer,
                "execution_time": execution_time,
                "intermediate_steps": {
                    "iterations": iteration,
                    "all_results": all_results,
                    "reasoning_chain": reasoning_chain
                }
            }

        except Exception as e:
            logger.error(f"Error in recursive KG query: {str(e)}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "answer": "I encountered an error while querying the knowledge graph.",
                "intermediate_steps": {"error": str(e)}
            }

    async def _arun(self, query: str) -> Dict[str, Any]:
        """Run the tool asynchronously."""
        # For simplicity, we'll just call the synchronous version
        return self._run(query)
