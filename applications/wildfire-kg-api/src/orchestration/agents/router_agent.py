from typing import Dict, List, Any, Tuple, Literal, Optional
import logging
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import os
import json
import re
from pydantic import BaseModel, Field

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the possible actions
RouterAction = Literal["kg_query", "rag_query", "both", "weather_query", "all", "direct_response"]


# Define the Pydantic model for structured output
class RouterOutput(BaseModel):
    action: RouterAction = Field(description="The action to take based on the query")
    reasoning: str = Field(description="The reasoning behind the action selection")


def create_router_agent(model_name: str = "gpt-3.5-turbo", temperature: float = 0.0):
    """Create a router agent that decides which tool to use based on the user query."""
    # Initialize the LLM
    llm = ChatOpenAI(
        model=model_name, temperature=temperature, api_key=os.getenv("OPENAI_API_KEY")
    )

    # Create a structured output LLM
    structured_llm = llm.with_structured_output(RouterOutput)

    # Define the prompt template with a simpler format
    router_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a router agent for a wildfire knowledge system. Your job is to analyze the user's query and decide which tool to use.

Choose from these options:
1. Knowledge Graph Query (kg_query): For queries about specific wildfire data or entities in our knowledge graph
2. RAG Query (rag_query): For queries needing up-to-date or general information not in our knowledge graph
3. Weather Query (weather_query): For queries about weather conditions, forecasts, or weather-related wildfire risks
4. Both KG and RAG (both): For queries needing both structured knowledge graph data AND general information
5. Direct Response (direct_response): For simple queries that don't need external data
6. All Tools (all): For queries requiring weather, historical data, and general information

Examples:
- "What's the average canopy height in the San Bernardino forest?" → kg_query
- "What are the current wildfire conditions in California?" → rag_query
- "How do forest density metrics correlate with wildfire risk, and what prevention recommendations exist?" → both
- "What's the temperature in Los Angeles?" → weather_query
- "How does current weather affect fire risk in Santa Barbara based on historical patterns?" → all
- "What is a wildfire?" → direct_response""",
            ),
            ("human", "{query}"),
        ]
    )

    def route(query: str) -> Dict[str, Any]:
        """Route the query to the appropriate tool."""
        try:
            logger.info(f"Routing query: {query}")

            # Use structured output to get a validated result
            result = structured_llm.invoke(router_prompt.format(query=query))

            logger.info(
                f"Router selected: {result.action} with reasoning: {result.reasoning}"
            )

            return {
                "action": result.action,
                "reasoning": result.reasoning,
            }

        except Exception as e:
            logger.error(f"Error in router agent: {str(e)}", exc_info=True)
            # Default to using both tools if there's an error
            return {
                "action": "all",
                "reasoning": f"Error occurred: {str(e)}. Defaulting to using all tools.",
            }

    return route
