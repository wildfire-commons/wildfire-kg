from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import boto3
import os
import logging
from botocore.exceptions import ClientError

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/storage",
    tags=["S3"],
    responses={
        200: {"description": "Successful response"},
        404: {"description": "Resource not found"},
        500: {"description": "Internal server error"},
    },
)

# TODO: FIX RUNNING WITH ENV VARIABLES IN DOCKER
s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            endpoint_url=os.getenv("AWS_S3_ENDPOINT_URL"),
        )

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


class GeneratePresignedUrlRequest(BaseModel):
    file_name: str


@router.get("/buckets", response_model=BucketListResponse)
async def list_buckets():
    """List all available S3 buckets in a directory tree format"""
    try:
        logger.debug("Attempting to list buckets")
        response = s3_client.list_buckets()

        buckets = [
            BucketInfo(name=bucket["Name"], created=bucket["CreationDate"].isoformat())
            for bucket in response["Buckets"]
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
        # Calculate parent prefix for navigation
        parent_prefix = None
        if prefix:
            parts = prefix.rstrip("/").split("/")
            if len(parts) > 1:
                parent_prefix = "/".join(parts[:-1]) + "/"
            elif len(parts) == 1:
                parent_prefix = ""

        # List objects with delimiter for folder-like structure
        response = s3_client.list_objects_v2(
            Bucket=bucket_name, Prefix=prefix, Delimiter="/"
        )

        objects = []

        # Add folders (CommonPrefixes)
        if "CommonPrefixes" in response:
            for prefix_obj in response["CommonPrefixes"]:
                folder_name = prefix_obj["Prefix"].rstrip("/").split("/")[-1]
                objects.append(
                    S3Object(
                        name=folder_name,
                        path=prefix_obj["Prefix"],
                        type="folder",
                        size=None,
                        modified=None,
                    )
                )

        # Add files
        if "Contents" in response:
            for obj in response["Contents"]:
                # Skip the prefix itself if it's a folder
                if obj["Key"] == prefix:
                    continue

                file_name = obj["Key"].split("/")[-1]
                objects.append(
                    S3Object(
                        name=file_name,
                        path=obj["Key"],
                        type="file",
                        size=obj["Size"],
                        modified=obj["LastModified"].isoformat(),
                    )
                )

        return S3ListResponse(
            objects=objects, prefix=prefix, parent_prefix=parent_prefix
        )

    except Exception as e:
        logger.error(f"Error listing objects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buckets/{bucket_name}/folders")
async def create_folder(bucket_name: str, prefix: str = Query(...)):
    """Create a new folder in the bucket"""
    try:
        # Ensure prefix ends with /
        if not prefix.endswith("/"):
            prefix += "/"

        # Create empty object with / suffix to represent folder
        s3_client.put_object(Bucket=bucket_name, Key=prefix)

        return {"message": "Folder created successfully", "path": prefix}

    except Exception as e:
        logger.error(f"Error creating folder: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/buckets/{bucket_name}/folders")
async def delete_folder(bucket_name: str, prefix: str = Query(...)):
    """Delete a folder and optionally all its contents"""
    try:
        # First, list objects to check if folder is empty
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        objects = []
        if "Contents" in response:
            objects = response["Contents"]

        # Delete all objects including the folder marker
        for obj in objects:
            s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])

        return {
            "message": "Folder deleted successfully",
            "deleted_objects_count": len(objects),
        }

    except Exception as e:
        logger.error(f"Error deleting folder: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buckets/{bucket_name}/presigned-url")
async def generate_presigned_url(
    bucket_name: str, request: GeneratePresignedUrlRequest
):
    """Generate a presigned URL for uploading a file to S3"""
    try:
        # Set up S3 client
        # Construct the full path for the file (only file_name is needed)
        file_key = request.file_name
        logger.debug(f"Generated file_key: {file_key}")

        # Generate the presigned URL using the format you specified
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",  # Specifies that the URL is for a PUT request
            Params={"Bucket": bucket_name, "Key": file_key},
            ExpiresIn=3600,  # Default expiration of 1 hour
        )

        logger.debug(f"Presigned URL: {presigned_url}")

        return {
            "presigned_url": presigned_url,
            "file_key": file_key,
            "expires_in": 3600,  # Default expiration time of 1 hour
        }

    except ClientError as e:
        logger.error(f"Error generating presigned URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buckets/{bucket_name}/download")
async def get_download_url(bucket_name: str, file_key: str = Query(...)):
    """Generate a presigned URL for downloading a file from S3"""
    try:
        # Generate the presigned URL for downloading
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_key
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        logger.debug(f"Generated download URL for {file_key}")
        return {"download_url": presigned_url}

    except ClientError as e:
        logger.error(f"Error generating download URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
