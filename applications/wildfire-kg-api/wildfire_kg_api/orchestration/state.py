from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    FunctionMessage,
)
from langgraph.graph import StateGraph


class State(BaseModel):
    """State of the conversation."""

    messages: List[Union[HumanMessage, AIMessage, SystemMessage, FunctionMessage]] = (
        Field(default_factory=list)
    )
    user_query: Optional[str] = None
    response: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationGraph(StateGraph):
    """Graph for managing conversation state."""

    def __init__(self):
        super().__init__(State)
