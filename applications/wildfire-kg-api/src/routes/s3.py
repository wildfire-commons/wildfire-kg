from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from botocore.exceptions import ClientError
import boto3
import os
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])

class BucketInfo(BaseModel):
    name: str
    created: str

class BucketListResponse(BaseModel):
    buckets: List[BucketInfo]

@router.get("/buckets", response_model=BucketListResponse)
async def list_buckets():
    """List all available S3 buckets in a directory tree format"""
    try:
        s3_client = boto3.client('s3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            endpoint_url=os.getenv('AWS_S3_ENDPOINT_URL')
        )
        
        logger.debug("Attempting to list buckets")
        response = s3_client.list_buckets()
        
        buckets = [
            BucketInfo(
                name=bucket['Name'],
                created=bucket['CreationDate'].isoformat()
            )
            for bucket in response['Buckets']
        ]
        
        logger.debug(f"Successfully listed {len(buckets)} buckets")
        return BucketListResponse(buckets=buckets)
            
    except Exception as e:
        logger.error(f"Error listing buckets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 