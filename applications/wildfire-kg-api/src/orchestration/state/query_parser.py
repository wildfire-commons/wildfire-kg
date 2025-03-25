from pydantic import BaseModel, Field
from typing import Optional, List
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import logging

logger = logging.getLogger(__name__)

class QueryComponents(BaseModel):
    """Structured components of a query."""
    metric_type: Optional[str] = Field(
        None, 
        description="The type of metric being queried (e.g., 'tree_count', 'shrub_height', 'canopy_density')"
    )
    aggregation: Optional[str] = Field(
        None, 
        description="The type of aggregation requested (e.g., 'average', 'maximum', 'minimum', 'total')"
    )
    entity_id: Optional[str] = Field(
        None, 
        description="Specific identifier for an entity (e.g., 'plot_CASBC_0045')"
    )
    entity_type: Optional[str] = Field(
        None, 
        description="Type of entity being queried (e.g., 'plot', 'forest_area', 'management_zone')"
    )
    temporal_context: Optional[str] = Field(
        None, 
        description="Time context of the query (e.g., '2024', 'latest', 'historical')"
    )
    comparison: Optional[str] = Field(
        None, 
        description="Comparison operation if any (e.g., 'greater_than', 'less_than', 'between')"
    )
    comparison_value: Optional[str] = Field(
        None, 
        description="Value for comparison if applicable"
    )

def create_query_parser(model_name: str = "gpt-3.5-turbo", temperature: float = 0.0):
    """Create a parser that extracts structured components from natural language queries."""
    llm = ChatOpenAI(model=model_name, temperature=temperature)
    structured_llm = llm.with_structured_output(QueryComponents)
    
    parser_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a query parser that extracts structured components from natural language queries about wildfire metrics.
            
            Examples:
            Query: "What is the average tree height in plot CASBC_0045?"
            Components: {
                "metric_type": "tree_height",
                "aggregation": "average",
                "entity_id": "plot_CASBC_0045",
                "entity_type": "plot"
            }
            
            Query: "Show me plots with shrub density greater than 50%"
            Components: {
                "metric_type": "shrub_density",
                "entity_type": "plot",
                "comparison": "greater_than",
                "comparison_value": "50%"
            }
            
            Query: "What are the tree shrub metric properties for plot wifire:plot_CASBC_0045_20240912_1?"
            Components: {
                "metric_type": "tree_shrub_metrics",
                "entity_id": "plot_CASBC_0045_20240912_1",
                "entity_type": "plot"
            }
            
            Extract only the components that are clearly present in the query. Leave other fields as null.
            Always return a valid JSON object with the defined fields, even if they are null."""
        ),
        ("human", "{query}")
    ])
    
    def parse(query: str) -> QueryComponents:
        """Parse the query and ensure valid output."""
        try:
            # Get the structured output
            result = structured_llm.invoke(parser_prompt.format(query=query))
            return result
        except Exception as e:
            logger.error(f"Error parsing query: {str(e)}", exc_info=True)
            # Return empty components if parsing fails
            return QueryComponents()
    
    return parse, parser_prompt 