from fastapi import Request
from fastapi.responses import Response
from functools import wraps
from typing import Callable

def cors_headers(request: Request) -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, X-Amz-Date, X-Amz-User-Agent, X-Amz-Security-Token, Content-Length",
        "Access-Control-Expose-Headers": "ETag",
        "Access-Control-Max-Age": "3600",
    }

def with_cors(endpoint: Callable):
    @wraps(endpoint)
    async def wrapper(request: Request, *args, **kwargs):
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers=cors_headers(request)
            )

        response = await endpoint(request, *args, **kwargs)
        
        # If response is already a Response object, add CORS headers
        if isinstance(response, Response):
            for key, value in cors_headers(request).items():
                response.headers[key] = value
            return response
            
        # If response is a dict/list, convert to Response with CORS headers
        return Response(
            content=response.body if hasattr(response, 'body') else response,
            status_code=response.status_code if hasattr(response, 'status_code') else 200,
            headers=cors_headers(request)
        )
        
    return wrapper 