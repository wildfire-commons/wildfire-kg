"""
Agent module for wildfire knowledge graph chatbot.
"""

import logging
from typing import Dict, Any, List, Optional, Union
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    FunctionMessage,
)
from langchain_core.tools import BaseTool
from langchain_core.runnables.config import RunnableConfig
from langchain_core.callbacks import StdOutCallbackHandler

from .state import State
from .tools import query_knowledge_graph, get_weather, web_search

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def get_all_tools() -> List[BaseTool]:
    """
    Get all available tools.
    Returns a list of tool functions decorated with @tool.
    """
    return [
        query_knowledge_graph,
        get_weather,
        web_search,
    ]


def get_system_prompt() -> str:
    """Get the system prompt for the ReAct agent."""
    return """
    You are a helpful assistant specializing in wildfire information, prevention, and management.
    Your goal is to provide accurate, helpful information about wildfires, their impacts, 
    prevention strategies, and related environmental topics.
    
    You have access to several tools:
    1. A knowledge graph with information about wildfires, their causes, and impacts
    2. A weather tool that can check current weather conditions that might affect fire risk
    3. A web search tool for finding recent or additional information on wildfires
    
    Guidelines for providing assistance:
    - For factual information about wildfires, use the knowledge graph tool first
    - For location-specific weather that might affect fire danger, use the weather tool
    - For recent events or information not in the knowledge graph, use the web search tool
    - Provide clear, concise information with appropriate context
    - If you're uncertain, acknowledge the limitations of your knowledge
    
    Prioritize public safety in your responses and provide helpful information that could
    assist in wildfire awareness, prevention, and safety.
    """


def create_wildfire_react_agent(config: Optional[RunnableConfig] = None) -> Any:
    """
    Create a ReAct agent for the wildfire knowledge graph.

    Args:
        config: Optional RunnableConfig for the agent. Can include:
            - callbacks: List of callback handlers
            - tags: List of tags for tracking
            - metadata: Dict of metadata
            - configurable: Dict of runtime settings

    Returns:
        A ReAct agent graph that can be invoked with messages
    """
    logger.info("Creating ReAct agent")

    # Default config if none provided
    if config is None:
        config = RunnableConfig(
            callbacks=[StdOutCallbackHandler()],
            tags=["wildfire-kg"],
            metadata={"version": "1.0.0"},
        )

    # Get runtime settings from config
    model_name = config.get("configurable", {}).get("model_name", "gpt-4")
    temperature = config.get("configurable", {}).get("temperature", 0.0)

    # Initialize the LLM with config
    llm = ChatOpenAI(
        model=model_name,
        temperature=temperature,
        callbacks=config.get("callbacks", []),
        tags=config.get("tags", []),
        metadata=config.get("metadata", {}),
    )

    # Get all tools
    tools = get_all_tools()

    # Get system prompt
    system_message = get_system_prompt()

    # Create and return the ReAct agent
    return create_react_agent(llm, tools, prompt=system_message)


def process_message(
    user_message: str,
    message_history: Optional[
        List[Union[HumanMessage, AIMessage, SystemMessage, FunctionMessage]]
    ] = None,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """
    Process a user message through the ReAct agent.

    Args:
        user_message: The message from the user
        message_history: Optional list of previous messages in LangChain format
        config: Optional RunnableConfig for the agent

    Returns:
        Dict with response and updated message history
    """
    logger.info(f"Processing message: {user_message}")

    # Create the agent with config
    agent = create_wildfire_react_agent(config)

    # Initialize message history if none provided
    if message_history is None:
        message_history = []

    # Add the current user message
    message_history.append(HumanMessage(content=user_message))

    # Invoke the agent with config
    logger.info("Invoking ReAct agent")
    result = agent.invoke({"messages": message_history}, config=config)
    logger.info("Agent execution completed")

    # Extract the final AI message
    ai_message = result["messages"][-1]
    ai_content = ai_message.content

    # Add the AI response to history
    message_history.append(ai_message)

    return {"response": ai_content, "messages": message_history}
