from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import os
import sys
import platform

from src.routes import s3_router

app = FastAPI(
    title="Wildfire Knowledge Graph API",
    description="API for interacting with the Wildfire Knowledge Graph",
    version="0.1.0",  # Updated version
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication setup (commented out for now)
# security = HTTPBearer()

# class AuthMiddleware:
#     async def __call__(self, request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
#         try:
#             # TODO: Implement token validation logic
#             # Example:
#             # - Verify JWT token
#             # - Check token expiration
#             # - Validate against user database
#             # token = credentials.credentials
#             # user = await validate_token(token)
#             # request.state.user = user
#             pass
#         except Exception as e:
#             raise HTTPException(
#                 status_code=401,
#                 detail="Invalid authentication credentials",
#                 headers={"WWW-Authenticate": "Bearer"},
#             )

# Include routers
app.include_router(s3_router, prefix="/api")


# Health check route
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify API status.
    Returns basic system information and API status.
    """
    # Initialize status
    status = "healthy"
    checks = {}

    # Check AWS/S3 connectivity if configured
    try:
        import boto3
        from botocore.exceptions import ClientError

        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_REGION", "us-west-2"),
            )

            # Simple HEAD request to test connectivity
            try:
                s3_client.list_buckets()
                checks["aws_s3"] = "connected"
            except ClientError as e:
                checks["aws_s3"] = f"error: {str(e)}"
                status = "degraded"
        else:
            checks["aws_s3"] = "not configured"
    except ImportError:
        checks["aws_s3"] = "boto3 not installed"

    # Check OpenAI connectivity if configured
    if os.getenv("OPENAI_API_KEY"):
        try:
            import openai

            openai.api_key = os.getenv("OPENAI_API_KEY")

            try:
                # Just check if the API is accessible without making a real request
                openai.models.list()
                checks["openai"] = "connected"
            except Exception as e:
                checks["openai"] = f"error: {str(e)}"
                status = "degraded"
        except ImportError:
            checks["openai"] = "openai package not installed"
    else:
        checks["openai"] = "not configured"

    # Memory check
    import psutil

    try:
        memory = psutil.virtual_memory()
        checks["memory"] = {
            "total": f"{memory.total / (1024**3):.2f} GB",
            "available": f"{memory.available / (1024**3):.2f} GB",
            "percent_used": f"{memory.percent}%",
        }

        # Set to degraded if memory usage is high
        if memory.percent > 90:
            status = "degraded"
            checks["memory"]["status"] = "critical"
        elif memory.percent > 75:
            checks["memory"]["status"] = "warning"
        else:
            checks["memory"]["status"] = "ok"
    except:
        checks["memory"] = "psutil error"

    # Return complete health information
    return {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "system_info": {
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "checks": checks,
    }


# Example protected route template (commented out)
# @app.get("/protected-route")
# async def protected_route(auth: AuthMiddleware = Depends()):
#     """
#     This is a template for a protected route that requires authentication
#     """
#     return {"message": "This is a protected route"}
