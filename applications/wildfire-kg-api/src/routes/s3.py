from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from typing import Optional

router = APIRouter(prefix="/s3", tags=["s3"])

class PresignedUrlRequest(BaseModel):
    path: str
    content_type: Optional[str] = "application/octet-stream"

@router.post("/presigned-url")
async def get_presigned_url(request: PresignedUrlRequest):
    """Generate a presigned URL for S3 file upload"""
    try:
        s3_client = boto3.client('s3')
        
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': 'wifire-kg-data',
                'Key': request.path,
                'ContentType': request.content_type
            },
            ExpiresIn=3600
        )
        
        return {
            "url": presigned_url,
            "expires_in": 3600
        }
        
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e)) 