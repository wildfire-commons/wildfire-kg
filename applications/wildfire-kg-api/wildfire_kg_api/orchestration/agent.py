"""
Agent module for wildfire knowledge graph chatbot.
"""

import os
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

from wildfire_kg_api.orchestration.tools import (
    query_knowledge_graph,
    get_weather,
    web_search,
)
from wildfire_kg_api.orchestration.prompts import get_prompt, refresh_prompts
from wildfire_kg_api.orchestration.logger import setup_logger, get_logger
from wildfire_kg_api.orchestration.models import (
    AVAILABLE_MODELS,
    BEST_MODEL_FALLBACK,
    is_openai_model,
    get_default_temperature,
    is_agent_compatible,
    get_llm_params_for_model,
)

# Load environment variables
load_dotenv()

# Initialize logger
setup_logger(verbose=True)
logger = get_logger("agent")


class ModelCompatibilityError(Exception):
    """Exception raised when a model is not compatible with the agent pattern."""

    pass


def get_all_tools() -> List[BaseTool]:
    """
    Get all available tools.
    Returns a list of tool functions decorated with @tool.
    """
    return [
        query_knowledge_graph,
        get_weather,
        web_search(),
    ]


def create_wildfire_react_agent(config: Optional[RunnableConfig] = None) -> Any:
    """
    Create a ReAct agent for the wildfire knowledge graph.

    Args:
        config: Optional RunnableConfig for the agent. Can include:
            - callbacks: List of callback handlers
            - tags: List of tags for tracking
            - metadata: Dict of metadata
            - configurable: Dict of runtime settings including:
                - agent_model_name: Name of the model to use for the agent
                - agent_temperature: Temperature setting for the agent
                - verbose: Whether to enable verbose logging
                - kg_model_name: Model to use for knowledge graph tool
                - kg_temperature: Temperature for knowledge graph tool
                # - weather_model_name: Model to use for weather tool
                # - weather_temperature: Temperature for weather tool
                # - web_search_model_name: Model to use for web search tool
                # - web_search_temperature: Temperature for web search tool

    Configuration Notes:
        - Model and temperature settings provided at creation time determine which LLM is used
        - The same config should be passed to both create_wildfire_react_agent() and agent.invoke()
        - The config passed to invoke() is forwarded to tools but doesn't change the agent's LLM

    Returns:
        A ReAct agent graph that can be invoked with messages
    """
    # Default config if none provided
    if not config:
        logger.info("No config provided, using default config")
        config = RunnableConfig(
            tags=["wildfire-kg"],
            metadata={"version": "1.0.0"},
            configurable={
                "verbose": False,  # Disable verbose logging by default
                "agent_model_name": BEST_MODEL_FALLBACK["agent"]["model"],
                "agent_temperature": BEST_MODEL_FALLBACK["agent"]["temperature"],
                "kg_model_name": BEST_MODEL_FALLBACK["kg_tool"]["model"],
                "kg_temperature": BEST_MODEL_FALLBACK["kg_tool"]["temperature"],
                # Commenting out weather and web search model configs since they don't use models *yet*
                # "weather_model_name": BEST_MODEL_FALLBACK["weather_tool"]["model"],
                # "weather_temperature": BEST_MODEL_FALLBACK["weather_tool"]["temperature"],
                # "web_search_model_name": BEST_MODEL_FALLBACK["web_search_tool"]["model"],
                # "web_search_temperature": BEST_MODEL_FALLBACK["web_search_tool"]["temperature"],
            },
        )
    else:
        logger.info(f"Creating graph with provided config.")

    logger.info(f"Graph config: {config}")

    # Get runtime settings from config
    agent_model_name = config["configurable"].get(
        "agent_model_name", BEST_MODEL_FALLBACK["agent"]["model"]
    )

    # Check if model is compatible with agent pattern
    if not is_agent_compatible(agent_model_name):
        error_msg = f"Model '{agent_model_name}' is not compatible with the ReAct agent pattern. Please use a compatible model."
        logger.error(error_msg)
        raise ModelCompatibilityError(error_msg)

    # Determine agent_temperature:
    # 1. From config's "agent_temperature"
    # 2. From BEST_MODEL_FALLBACK for the agent
    # 3. Default temperature from the model itself (via get_default_temperature, which can be None)
    agent_temperature_config = config["configurable"].get("agent_temperature")
    if agent_temperature_config is None:
        agent_temperature_config = BEST_MODEL_FALLBACK["agent"].get("temperature")
    # Note: agent_temperature_config can still be None here if not in BEST_MODEL_FALLBACK
    # get_llm_params_for_model will handle None temperature_override correctly

    verbose = config["configurable"].get("verbose", False)

    # Set up logger based on verbose flag
    setup_logger(verbose=verbose)
    logger.info(
        f"Attempting to create ReAct agent with model: {agent_model_name}, requested temperature: {agent_temperature_config}"
    )

    # Initialize the LLM with config using the new helper
    llm_params = get_llm_params_for_model(
        model_name=agent_model_name,
        temperature_override=agent_temperature_config,
        callbacks=config.get("callbacks", []),
        tags=config.get("tags", []),
        metadata=config.get("metadata", {}),
        verbose=verbose,  # Pass verbose flag to LLM if it supports it (ChatOpenAI does)
    )

    logger.info(f"Final LLM params for agent: {llm_params}")
    llm = ChatOpenAI(**llm_params)

    # Get all tools
    tools = get_all_tools()

    # Initialize and get the prompt template
    try:
        # Force refresh of prompts to ensure they're loaded
        refresh_prompts()
        agent_prompt = get_prompt("agents.agent_prompt").template
        if agent_prompt is None:
            error_msg = "Failed to load agent prompt template. Please check that the prompt file exists and is correctly formatted."
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.debug("Successfully loaded agent prompt template")

        # Create and return the ReAct agent
        return create_react_agent(llm, tools, prompt=agent_prompt)
    except Exception as e:
        error_msg = f"Error initializing agent prompts: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


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
        # Add system message if not present
        if not any(isinstance(msg, SystemMessage) for msg in message_history):
            system_prompt = get_prompt("agents.agent_prompt")
            message_history.insert(0, SystemMessage(content=system_prompt))

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
