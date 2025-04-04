from typing import Dict, List, Optional, Any, TypedDict, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class Message(BaseModel):
    """Message in a conversation."""

    content: str
    role: Literal["human", "ai", "system", "function"]
    name: Optional[str] = None
    additional_kwargs: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphResult(BaseModel):
    """Result from a knowledge graph query."""

    query: str
    results: List[Dict[str, Any]]
    execution_time: float


class WebSearchResult(BaseModel):
    """Result from a web search query."""

    query: str
    documents: List[Dict[str, Any]]
    source: str


class WeatherResult(BaseModel):
    """Result from a weather query."""
    query: str
    location: Optional[str]
    weather_data: Dict[str, Any]
    execution_time: float


class ConversationState(TypedDict, total=False):
    """State of the conversation."""

    # The messages in the conversation
    messages: List[Message]

    # The current user query
    user_query: str

    # Knowledge graph results
    kg_results: Optional[KnowledgeGraphResult]

    # Web search results
    web_search_results: Optional[WebSearchResult]

    # The final response to return to the user
    response: Optional[str]

    # Any errors that occurred during processing
    error: Optional[str]

    # Metadata about the conversation
    metadata: Dict[str, Any]

    # Weather results
    weather_results: Optional[WeatherResult]
