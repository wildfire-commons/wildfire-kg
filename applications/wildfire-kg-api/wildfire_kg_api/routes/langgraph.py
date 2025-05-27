from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
from wildfire_kg_api.orchestration.agent import create_wildfire_react_agent
from wildfire_kg_api.orchestration.state import State

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
    pass

class ThreadCreateResponse(BaseModel):
    """Response model for thread creation."""
    thread_id: str

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

@router.post("/threads", response_model=ThreadCreateResponse)
async def create_thread(request: ThreadCreateRequest):
    """Create a new conversation thread."""
    try:
        # Generate a unique thread ID
        thread_id = str(uuid.uuid4())
        return ThreadCreateResponse(thread_id=thread_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/threads/{thread_id}/runs", response_model=RunResponse)
async def run_thread(thread_id: str, request: RunRequest):
    """Run a thread with the given input."""
    try:
        # Create the agent graph
        agent_graph = create_wildfire_react_agent()
        
        # Initialize state with the user query
        state = State(messages=[])
        state.user_query = request.input.get("user_query")
        
        # Add history if provided
        if "history" in request.input:
            for msg in request.input["history"]:
                state.messages.append({
                    "role": msg["sender"],
                    "content": msg["text"]
                })
        
        # Run the graph
        result = await agent_graph.ainvoke({"messages": state.messages})
        
        # Extract results
        response = RunResponse(
            messages=result.get("messages", []),
            kg_results=result.get("kg_results"),
            rag_results=result.get("rag_results"),
            weather_results=result.get("weather_results")
        )
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 