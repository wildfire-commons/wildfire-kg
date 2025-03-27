from typing import Dict, List, Any, Tuple, Literal, Optional
import logging
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import os
import json
import re
from pydantic import BaseModel, Field

# Import the prompt registry
from ..prompts import get_prompt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the possible actions
RouterAction = Literal["kg_query", "rag_query", "both", "direct_response"]


# Define the Pydantic model for structured output
class RouterOutput(BaseModel):
    action: RouterAction = Field(description="The action to take based on the query")
    reasoning: str = Field(description="The reasoning behind the action selection")


def create_router_agent(model_name: str = "gpt-4o-mini", temperature: float = 0.0):
    """Create a router agent that decides which tool to use based on the user query."""
    # Initialize the LLM
    llm = ChatOpenAI(
        model=model_name, temperature=temperature, api_key=os.getenv("OPENAI_API_KEY")
    )

    # Create a structured output LLM
    structured_llm = llm.with_structured_output(RouterOutput)

    # Get the prompt template from the registry
    router_prompt = get_prompt("agents.router_prompt")
    if not router_prompt:
        raise ValueError(
            "Router prompt not found. Please ensure it exists in the agents directory."
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
                "action": "both",
                "reasoning": f"Error occurred: {str(e)}. Defaulting to using both tools.",
            }

    return route
