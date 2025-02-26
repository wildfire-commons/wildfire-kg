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

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Get OpenAI API key
# openai_api_key = os.getenv('OPENAI_API_KEY')
# if not openai_api_key:
#     raise ValueError("OPENAI_API_KEY environment variable is not set")

router = APIRouter(prefix="/graph", tags=["graph"])

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

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat with the knowledge graph using natural language"""
    try:
        logger.debug(f"Received chat request: {request}")
        
        # First, query the graph for relevant context
        # TODO: Implement actual graph query based on message content
        context = {
            "recent_metrics": "Latest TLS metrics show average canopy height of 25m",
            "data_sources": "3 LiDAR point clouds from recent surveys",
            "graph_data": "Sample data from Neo4j knowledge graph"
        }
        logger.debug(f"Retrieved context from graph: {context}")

        # Create prompt template that emphasizes graph-based responses
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful assistant specializing in wildfire and forest data analysis. 
            Use the following context from our knowledge graph to answer questions: {context}
            Always try to reference specific data points and metrics from the graph when possible."""),
            ("human", "{input}")
        ])

        # Set up LangChain with graph-aware context
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0,
            api_key=os.getenv('OPENAI_API_KEY')
        )
        
        chain = LLMChain(
            llm=llm,
            prompt=prompt
        )

        # Generate response using graph context
        logger.debug(f"Generating response for input: {request.message}")
        response = chain.run(
            context=str(context),
            input=request.message
        )
        logger.debug(f"Generated response: {response}")

        return ChatResponse(
            message=ChatMessage(
                id="response-1",
                text=response,
                sender="assistant",
                timestamp=datetime.now().isoformat()
            ),
            context=context
        )

    except Exception as e:
        logger.error(f"Error in graph chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query")
async def natural_language_query(query: NaturalLanguageQuery):
    """Query the knowledge graph using natural language"""
    try:
        # Here we would integrate with an LLM to convert natural language to Cypher
        # For now, we'll use a mock implementation
        records = [
            {"name": "Sample Plot 1", "canopy_height": 25},
            {"name": "Sample Plot 2", "canopy_height": 30}
        ]
        
        return GraphResponse(
            results=records,
            query_type="similarity_search",
            execution_time=0.0
        )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 