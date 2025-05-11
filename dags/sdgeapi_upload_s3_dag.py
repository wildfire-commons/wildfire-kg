import os
import requests
import json
import pandas as pd
import boto3
from botocore.client import Config
from typing import Optional
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from datetime import datetime

wfs_url = "https://sdge.sdsc.edu/geoserver/wfs?service=wfs&version=1.0.0&request=GetFeature&outputFormat=application/json&typeName=SDGE:intelimon_metrics"

def fetch_and_clean_data() -> Optional[str]:
    print(f"Fetching data from: {wfs_url}")
    response = requests.get(wfs_url)

    if not response.ok:
        print(f"Failed to fetch data: {response.status_code}")
        return None

    data = response.json()
    features = data.get("features", [])
    if not features:
        print("No features found.")
        return None

    props = [f["properties"] for f in features]
    df_raw = pd.DataFrame(props)

    df_metrics = df_raw['metrics'].dropna().apply(json.loads).apply(pd.Series)

    # Combine plot_name with cleaned metrics
    df_clean = pd.concat([
        df_raw.loc[df_metrics.index, 'plot_name'].reset_index(drop=True),
        df_metrics.reset_index(drop=True)
    ], axis=1)

    df_clean.rename(columns={'plot_name': 'PLOT_NAME'}, inplace=True)

    output_filename = "cleaned_intelimon_metrics.csv"
    df_clean.to_csv(output_filename, index=False)
    print(f"Saved cleaned file as: {output_filename}")

    return output_filename

def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=Variable.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=Variable.get("AWS_SECRET_ACCESS_KEY"),
        endpoint_url=Variable.get("AWS_S3_ENDPOINT_URL"),
        config=Config(signature_version="s3v4")
    )

def generate_presigned_put_url(bucket: str, key: str, expiration: int = 3600) -> Optional[str]:
    try:
        s3_client = get_s3_client()
        url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Failed to generate presigned URL: {e}")
        return None

def upload_to_s3_with_presigned_url(file_path: str, bucket: str, object_key: str):
    url = generate_presigned_put_url(bucket, object_key)
    if not url:
        print("Presigned URL generation failed.")
        return

    try:
        with open(file_path, "rb") as f:
            file_data = f.read()
            headers = {
                "Content-Length": str(len(file_data)),
                "Content-Type": "text/csv"
            }

            response = requests.put(url, data=file_data, headers=headers)

            if response.status_code == 200:
                print(f"Uploaded {file_path} to s3://{bucket}/{object_key}")
            else:
                print(f"Upload failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"Error uploading to S3: {e}")

def fetch_and_upload():
    cleaned_file_path = fetch_and_clean_data()
    if not cleaned_file_path:
        print("Skipping upload.")
        return

    try:
        bucket = Variable.get("AWS_S3_BUCKET_NAME")
    except KeyError:
        print("AWS_S3_BUCKET_NAME variable not set in Airflow.")
        return

    object_key = os.path.basename(cleaned_file_path)

    print(f"File path: {cleaned_file_path}")
    print(f"Bucket: {bucket}")
    print(f"Object key: {object_key}")

    upload_to_s3_with_presigned_url(cleaned_file_path, bucket, object_key)

def ensure_variables():
    """Ensure all required variables are set"""
    required_vars = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_S3_ENDPOINT_URL",
        "AWS_S3_BUCKET_NAME"
    ]
    
    for var in required_vars:
        try:
            Variable.get(var)
        except KeyError:
            print(f"Required variable {var} is not set")
            return False
    return True

# Airflow DAG definition
with DAG(
    dag_id="sdgeapi_upload_to_s3",
    description="Fetch SDGE data and upload to S3",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False
) as dag:

    check_vars = PythonOperator(
        task_id="check_variables",
        python_callable=ensure_variables
    )

    upload_task = PythonOperator(
        task_id="fetch_clean_upload",
        python_callable=fetch_and_upload
    )

    check_vars >> upload_task
