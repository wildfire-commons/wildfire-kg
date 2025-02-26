from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from datetime import datetime
import logging
import os
from dotenv import load_dotenv

# Import the LangGraph orchestration
from ..orchestration import process_user_message, Message, ConversationState

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create router with updated prefix
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    id: str
    text: str
    sender: str
    timestamp: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []


class ChatResponse(BaseModel):
    message: ChatMessage
    context: Optional[dict] = None


class NaturalLanguageQuery(BaseModel):
    query: str


class GraphResponse(BaseModel):
    results: List[dict]
    query_type: str
    execution_time: float


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat with the knowledge graph using natural language"""
    try:
        logger.debug(f"Received chat request: {request}")

        # Convert the chat history to LangGraph Message format
        conversation_history = []
        for msg in request.history:
            role = "human" if msg.sender == "user" else "ai"
            conversation_history.append(Message(content=msg.text, role=role))

        # Process the message using LangGraph
        result = process_user_message(request.message, conversation_history)

        # Extract the response
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        response_text = result.get(
            "response", "I'm sorry, I couldn't generate a response."
        )

        # Extract context information
        context = {
            "kg_results": result.get("kg_results", {}),
            "rag_results": result.get("rag_results", {}),
            "routing": result.get("metadata", {}).get("routing", {}),
        }

        logger.debug(f"Generated response: {response_text}")

        return ChatResponse(
            message=ChatMessage(
                id=f"response-{datetime.now().timestamp()}",
                text=response_text,
                sender="assistant",
                timestamp=datetime.now().isoformat(),
            ),
            context=context,
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query")
async def natural_language_query(query: NaturalLanguageQuery):
    """Query the knowledge graph using natural language"""
    try:
        # Here we would integrate with an LLM to convert natural language to Cypher
        # For now, we'll use a mock implementation
        records = [
            {"name": "Sample Plot 1", "canopy_height": 25},
            {"name": "Sample Plot 2", "canopy_height": 30},
        ]

        return GraphResponse(
            results=records, query_type="similarity_search", execution_time=0.0
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
