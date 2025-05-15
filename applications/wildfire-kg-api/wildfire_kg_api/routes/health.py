"""
Health check routes for monitoring API status.
"""

from fastapi import APIRouter, Depends
from datetime import datetime
import os
import sys
import platform

# Create a router for health check endpoints
router = APIRouter(
    tags=["Health"],
    prefix="",
    responses={
        200: {"description": "Successful response"},
        500: {"description": "Internal server error"},
    },
)


@router.get("/health", summary="Health check endpoint")
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
    try:
        import psutil

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
    except Exception as e:
        checks["memory"] = f"error: {str(e)}"

    # Get API version - using environment variable or fixed value
    # to avoid circular imports with app
    api_version = os.getenv("API_VERSION", "0.1.0")

    # Return complete health information
    return {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "version": api_version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "system_info": {
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "checks": checks,
    }


@router.get("/health/ping", summary="Simple ping endpoint")
async def ping():
    """
    Simple ping endpoint for basic connectivity testing.
    Useful for load balancers and simple health checks.
    """
    return {"ping": "pong", "timestamp": datetime.now().isoformat()}


@router.get("/health/ready", summary="Readiness probe")
async def readiness_check():
    """
    Readiness probe for Kubernetes and other orchestration systems.
    Indicates if the service is ready to accept traffic.
    """
    # Perform a minimal check - more extensive checks in the main health endpoint
    try:
        # Add any critical service check here
        return {"status": "ready", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {
            "status": "not ready",
            "reason": str(e),
            "timestamp": datetime.now().isoformat(),
        }
