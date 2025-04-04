from typing import Dict, List, Any, Optional
import logging
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import os
from src.orchestration.state.conversation_state import ConversationState, Message

# Import the prompt registry
from src.orchestration.prompts import get_prompt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_response_agent(model_name: str = "gpt-3.5-turbo", temperature: float = 0.7):
    """Create a response agent that generates the final response to the user."""
    # Initialize the LLM
    llm = ChatOpenAI(
        model=model_name, temperature=temperature, api_key=os.getenv("OPENAI_API_KEY")
    )

    # Define the prompt template
    response_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a helpful assistant specializing in wildfire and forest data analysis. 
        Your goal is to provide informative, accurate responses based on the available information.
        
        You have access to three types of information:
        1. Knowledge Graph Results: Structured data from our wildfire knowledge graph
        2. RAG Results: Information retrieved from external sources
        3. Weather Data: Current weather conditions and forecasts
        
        Guidelines:
        - Synthesize information from all available sources
        - For weather queries, focus on weather data and its implications for fire risk
        - Clearly attribute information to its source
        - Be honest about limitations in the data
        - Use a conversational, helpful tone
        - If the information is incomplete, acknowledge this and suggest what additional data might help
        - Format your response in a clear, readable way
        
        Knowledge Graph Results: {kg_results}
        RAG Results: {rag_results}
        Weather Results: {weather_results}
        
        Previous conversation context: {conversation_history}
        """,
            ),
            ("human", "{query}"),
        ]
    )

    def generate_response(state: ConversationState) -> str:
        """Generate a response based on the conversation state."""
        try:
            # Extract the relevant information from the state
            query = state.get("user_query", "")
            kg_results = state.get("kg_results", {})
            rag_results = state.get("rag_results", {})
            weather_results = state.get("weather_results", {})
            messages = state.get("messages", [])
            metadata = state.get("metadata", {})

            # Log what we're working with
            logger.info(f"Generating response for query: {query}")
            logger.info(f"KG results available: {bool(kg_results)}")
            logger.info(f"RAG results available: {bool(rag_results)}")
            logger.info(f"Weather results available: {bool(weather_results)}")

            # Check if we're coming from the "both" node
            both_executed = metadata.get("both_executed", False)
            if both_executed:
                logger.info("Processing results from 'both' node execution")
                kg_success = metadata.get("kg_success", False)
                web_search_success = metadata.get("web_search_success", False)
                logger.info(
                    f"KG query success: {kg_success}, Web search query success: {web_search_success}"
                )

            # Format the conversation history
            conversation_history = ""
            for msg in messages[
                -6:
            ]:  # Only use the last 6 messages to avoid context length issues
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                else:
                    role = msg.role
                    content = msg.content
                conversation_history += f"{role.capitalize()}: {content}\n"

            # Generate the response
            logger.info("Invoking LLM for response generation")
            response = llm.invoke(
                response_prompt.format(
                    query=query,
                    kg_results=(
                        kg_results
                        if kg_results and "error" not in kg_results
                        else "No knowledge graph results available."
                    ),
                    rag_results=(
                        rag_results
                        if rag_results and "error" not in rag_results
                        else "No RAG results available."
                    ),
                    weather_results=(
                        weather_results
                        if weather_results and "error" not in weather_results
                        else "No weather data available."
                    ),
                    conversation_history=conversation_history,
                )
            )

            logger.info("Response generated successfully")
            return response.content

        except Exception as e:
            logger.error(f"Error in response agent: {str(e)}", exc_info=True)
            return f"I apologize, but I encountered an error while generating a response: {str(e)}. Please try again or rephrase your question."

    return generate_response
