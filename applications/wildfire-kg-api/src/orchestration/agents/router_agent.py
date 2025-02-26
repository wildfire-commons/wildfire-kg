from typing import Dict, List, Any, Tuple, Literal, Optional
import logging
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import os
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the possible actions
RouterAction = Literal["kg_query", "rag_query", "both", "direct_response"]


def create_router_agent(model_name: str = "gpt-3.5-turbo", temperature: float = 0.0):
    """Create a router agent that decides which tool to use based on the user query."""
    # Initialize the LLM
    llm = ChatOpenAI(
        model=model_name, temperature=temperature, api_key=os.getenv("OPENAI_API_KEY")
    )

    # Define the prompt template
    router_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a router agent for a wildfire knowledge system. Your job is to analyze the user's query and decide which tool to use:

1. Knowledge Graph Query (kg_query): Use when the query is about specific wildfire data, forest metrics, or entities that would be stored in our knowledge graph.
2. RAG Query (rag_query): Use when the query requires up-to-date information from external sources, general knowledge, or information that wouldn't be in our knowledge graph.
3. Both (both): Use when the query would benefit from both knowledge graph data and external information.
4. Direct Response (direct_response): Use when the query can be answered directly without needing to query any tools.

Examples:
- "What's the average canopy height in the San Bernardino forest?" -> kg_query
- "What are the current wildfire conditions in California?" -> rag_query
- "How do forest density metrics correlate with wildfire risk, and what are the latest recommendations for prevention?" -> both
- "What is a wildfire?" -> direct_response

Respond with a JSON object with the following structure:
{
  "action": "kg_query" | "rag_query" | "both" | "direct_response",
  "reasoning": "Your step-by-step reasoning for choosing this action"
}""",
            ),
            ("human", "{query}"),
        ]
    )

    def route(query: str) -> Dict[str, Any]:
        """Route the query to the appropriate tool."""
        try:
            # Get the router's decision
            response = llm.invoke(router_prompt.format(query=query))

            # Parse the response
            content = response.content

            # Extract the JSON part if needed
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Parse the JSON
            result = json.loads(content)

            # Validate the action
            action = result.get("action")
            if action not in ["kg_query", "rag_query", "both", "direct_response"]:
                logger.warning(f"Invalid action: {action}. Defaulting to 'both'.")
                action = "both"

            return {
                "action": action,
                "reasoning": result.get("reasoning", "No reasoning provided"),
            }

        except Exception as e:
            logger.error(f"Error in router agent: {str(e)}", exc_info=True)
            # Default to using both tools if there's an error
            return {
                "action": "both",
                "reasoning": f"Error occurred: {str(e)}. Defaulting to using both tools.",
            }

    return route
