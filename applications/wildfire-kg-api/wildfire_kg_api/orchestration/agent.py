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

from wildfire_kg_api.orchestration.tools import (
    query_knowledge_graph,
    get_weather,
    web_search,
)
from wildfire_kg_api.orchestration.prompts import get_prompt

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
    model_name = config.get("configurable", {}).get("model_name", "gpt-4o-mini")
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

    # Get the prompt template
    agent_prompt = get_prompt("agents.agent_prompt").template

    # Create and return the ReAct agent
    return create_react_agent(llm, tools, prompt=agent_prompt)


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
