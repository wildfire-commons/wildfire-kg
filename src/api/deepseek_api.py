from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import json

app = FastAPI()

class Query(BaseModel):
    prompt: str
    max_tokens: int = 1024
    temperature: float = 0.7

class Response(BaseModel):
    text: str

@app.post("/generate")
async def generate_text(query: Query):
    try:
        # DeepSeek LLM endpoint
        response = requests.post(
            "http://deepseek-llm:8080/v1/completions",
            json={
                "prompt": query.prompt,
                "max_tokens": query.max_tokens,
                "temperature": query.temperature
            }
        )
        return Response(text=response.json()["choices"][0]["text"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"} 