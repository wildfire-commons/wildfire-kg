from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
import requests

router = APIRouter(prefix="/graph", tags=["graph"])

class NaturalLanguageQuery(BaseModel):
    query: str
    max_results: Optional[int] = 10

class GraphResponse(BaseModel):
    results: List[Dict]
    query_type: str
    execution_time: float

@router.post("/query")
async def natural_language_query(query: NaturalLanguageQuery):
    """Query the knowledge graph using natural language"""
    try:
        # Here we would integrate with an LLM to convert natural language to Cypher
        # For now, we'll use a mock implementation
        cypher_query = "MATCH (n) WHERE n.description CONTAINS $query RETURN n LIMIT $limit"
        
        # Execute query against Neo4j
        # Using the credentials from your existing Neo4j setup
        from neo4j import GraphDatabase
        
        URI = "neo4j://neo4j:7687"  # Using internal k8s service name
        AUTH = ("neo4j", "$zajf9s9eDOLECntRxK5Mded")  # From your neo4j.yaml
        
        driver = GraphDatabase.driver(URI, auth=AUTH)
        
        with driver.session() as session:
            result = session.run(
                cypher_query,
                query=query.query,
                limit=query.max_results
            )
            records = [record.data() for record in result]
            
        return GraphResponse(
            results=records,
            query_type="similarity_search",
            execution_time=0.0  # In a real implementation, we'd measure this
        )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 