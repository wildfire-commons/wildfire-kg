from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from botocore.exceptions import ClientError
import boto3
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])

class BucketInfo(BaseModel):
    name: str
    created: str

class BucketListResponse(BaseModel):
    buckets: List[BucketInfo]

class S3Object(BaseModel):
    name: str
    path: str
    type: str  # 'folder' or 'file'
    size: Optional[int]
    modified: Optional[str]

class S3ListResponse(BaseModel):
    objects: List[S3Object]
    prefix: str
    parent_prefix: Optional[str]

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

@router.get("/buckets/{bucket_name}/objects", response_model=S3ListResponse)
async def list_objects(bucket_name: str, prefix: str = Query(default="")):
    """List objects in a bucket with folder navigation"""
    try:
        s3_client = boto3.client('s3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            endpoint_url=os.getenv('AWS_S3_ENDPOINT_URL')
        )
        
        # Calculate parent prefix for navigation
        parent_prefix = None
        if prefix:
            parts = prefix.rstrip('/').split('/')
            if len(parts) > 1:
                parent_prefix = '/'.join(parts[:-1]) + '/'
            elif len(parts) == 1:
                parent_prefix = ""

        # List objects with delimiter for folder-like structure
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            Delimiter='/'
        )
        
        objects = []
        
        # Add folders (CommonPrefixes)
        if 'CommonPrefixes' in response:
            for prefix_obj in response['CommonPrefixes']:
                folder_name = prefix_obj['Prefix'].rstrip('/').split('/')[-1]
                objects.append(S3Object(
                    name=folder_name,
                    path=prefix_obj['Prefix'],
                    type='folder',
                    size=None,
                    modified=None
                ))
        
        # Add files
        if 'Contents' in response:
            for obj in response['Contents']:
                # Skip the prefix itself if it's a folder
                if obj['Key'] == prefix:
                    continue
                    
                file_name = obj['Key'].split('/')[-1]
                objects.append(S3Object(
                    name=file_name,
                    path=obj['Key'],
                    type='file',
                    size=obj['Size'],
                    modified=obj['LastModified'].isoformat()
                ))
        
        return S3ListResponse(
            objects=objects,
            prefix=prefix,
            parent_prefix=parent_prefix
        )
            
    except Exception as e:
        logger.error(f"Error listing objects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/buckets/{bucket_name}/folders")
async def create_folder(bucket_name: str, prefix: str = Query(...)):
    """Create a new folder in the bucket"""
    try:
        s3_client = boto3.client('s3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            endpoint_url=os.getenv('AWS_S3_ENDPOINT_URL')
        )
        
        # Ensure prefix ends with /
        if not prefix.endswith('/'):
            prefix += '/'
            
        # Create empty object with / suffix to represent folder
        s3_client.put_object(
            Bucket=bucket_name,
            Key=prefix
        )
        
        return {"message": "Folder created successfully", "path": prefix}
            
    except Exception as e:
        logger.error(f"Error creating folder: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 