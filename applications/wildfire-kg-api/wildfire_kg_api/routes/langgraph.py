from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
from wildfire_kg_api.orchestration.agent import create_wildfire_react_agent
from wildfire_kg_api.orchestration.state import State
from langchain_core.messages import BaseMessage
from datetime import datetime

router = APIRouter(
    tags=["LangGraph"],
    responses={
        200: {"description": "Successful response"},
        404: {"description": "Resource not found"},
        500: {"description": "Internal server error"},
    },
)

class ThreadCreateRequest(BaseModel):
    """Request model for creating a new thread."""
    initial_message: str

class ThreadCreateResponse(BaseModel):
    """Response model for thread creation."""
    thread_id: str
    messages: List[Dict[str, Any]]
    # kg_results: Optional[Dict[str, Any]] = None
    # rag_results: Optional[Dict[str, Any]] = None
    # weather_results: Optional[Dict[str, Any]] = None

class RunRequest(BaseModel):
    """Request model for running a thread."""
    assistant_id: str
    input: Dict[str, Any]

class RunResponse(BaseModel):
    """Response model for thread run."""
    messages: List[Dict[str, Any]]
    kg_results: Optional[Dict[str, Any]] = None
    rag_results: Optional[Dict[str, Any]] = None
    weather_results: Optional[Dict[str, Any]] = None

def serialize_message(msg):
    out = {}
    if isinstance(msg, dict):
        out = msg.copy()
    elif isinstance(msg, BaseMessage): # Handle LangChain message objects
        out = {
            "type": msg.type,
            "content": msg.content,
            "additional_kwargs": msg.additional_kwargs.copy() # Make a copy
        }
        # Promote timestamp from additional_kwargs if present
        if "timestamp" in msg.additional_kwargs:
            out["timestamp"] = msg.additional_kwargs["timestamp"]
    else: # Fallback for other types
        out = {k: v for k, v in msg.__dict__.items() if not k.startswith('_')}

    # Add timestamp if not present at top level
    if 'timestamp' not in out or not out['timestamp']:
        out['timestamp'] = datetime.now().isoformat()
    return out

@router.post("/threads", response_model=ThreadCreateResponse)
async def create_thread(request: ThreadCreateRequest):
    """Create a new conversation thread and run initial message."""
    try:
        thread_id = str(uuid.uuid4())
        agent_graph = create_wildfire_react_agent()
        state = State(messages=[])
        state.user_query = request.initial_message
        user_msg_time = datetime.now().isoformat()
        # Pass timestamp directly for the initial user message dict
        state.messages.append({
            "role": "user",
            "content": request.initial_message,
            "timestamp": user_msg_time
        })
        result = await agent_graph.ainvoke({"messages": state.messages})
        messages = [serialize_message(m) for m in result.get("messages", [])]
        return ThreadCreateResponse(
            thread_id=thread_id,
            messages=messages,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/threads/{thread_id}/runs", response_model=RunResponse)
async def run_thread(thread_id: str, request: RunRequest):
    """Run a thread with the given input."""
    try:
        agent_graph = create_wildfire_react_agent()
        state = State(messages=[])
        state.user_query = request.input.get("user_query")
        current_time = datetime.now().isoformat()
        if "history" in request.input:
            filtered_history = [msg for msg in request.input["history"] if msg.get("text") and msg["text"].strip()]
            for idx, msg in enumerate(filtered_history):
                role = "user" if idx % 2 == 0 else "assistant"
                # Ensure history messages also have timestamps
                timestamp = msg.get("timestamp") or current_time
                state.messages.append({
                    "role": role,
                    "content": msg["text"],
                    "timestamp": timestamp
                })
        # Add the current user query with a fresh timestamp
        state.messages.append({
            "role": "user",
            "content": request.input.get("user_query"),
            "timestamp": datetime.now().isoformat()
        })
        result = await agent_graph.ainvoke({"messages": state.messages})
        messages = [serialize_message(m) for m in result.get("messages", [])]
        return RunResponse(
            messages=messages,
            kg_results=result.get("kg_results"),
            rag_results=result.get("rag_results"),
            weather_results=result.get("weather_results")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 