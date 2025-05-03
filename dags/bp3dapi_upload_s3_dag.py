import os
import requests
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import boto3
from botocore.client import Config
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from typing import Optional

BASE_URL = "https://burnpro3d.sdsc.edu/api/v1"

def get_bp3d_token() -> Optional[str]:
    username = Variable.get("BP3D_USERNAME")
    password = Variable.get("BP3D_PASSWORD")

    login_url = f"{BASE_URL}/user/login"
    payload = {
        "username": username,
        "password": password
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(login_url, data=payload, headers=headers, timeout=30)
        if response.ok:
            data = response.json()
            token = data.get("access_token")
            print("Successfully obtained BP3D token.")
            return token
        else:
            print(f"Failed to login: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"Error during login: {e}")
        return None

def generate_presigned_put_url(bucket: str, key: str, expiration: int = 3600) -> Optional[str]:
    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=Variable.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=Variable.get("AWS_SECRET_ACCESS_KEY"),
            endpoint_url=Variable.get("AWS_S3_ENDPOINT_URL"),
            config=Config(signature_version="s3v4")
        )
        return s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration
        )
    except Exception as e:
        print(f"Failed to generate presigned URL: {e}")
        return None

def upload_to_s3(file_path: str, bucket: str):
    object_key = os.path.basename(file_path)
    url = generate_presigned_put_url(bucket, object_key)
    if not url:
        print(f"Failed to generate presigned URL for {object_key}.")
        return

    try:
        with open(file_path, "rb") as f:
            file_data = f.read()
        headers = {
            "Content-Length": str(len(file_data)),
            "Content-Type": "application/geo+json"
        }
        response = requests.put(url, data=file_data, headers=headers)

        if response.status_code == 200:
            print(f"Uploaded {file_path} to s3://{bucket}/{object_key}")
        else:
            print(f"Upload failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"Error uploading to S3: {e}")

def fetch_bp3d_sensor_data(start_date_str: str = "2025-04-01T00:00:00+00:00", window_days: int = 30, extra_hours: int = 2):
    token = get_bp3d_token()
    if not token:
        print("Token retrieval failed. Aborting.")
        return

    start_date = datetime.strptime(start_date_str, "%Y-%m-%dT%H:%M:%S%z")
    end_date = datetime.now(timezone.utc)
    current_start = start_date

    bucket = Variable.get("AWS_S3_BUCKET_NAME")
    if not bucket:
        print("AWS_S3_BUCKET_NAME Airflow variable not set.")
        return

    while current_start < end_date:
        current_end = current_start + timedelta(days=window_days, hours=extra_hours)
        payload = {
            "start_time": current_start.isoformat(),
            "end_time": current_end.isoformat()
        }

        print(f"\nFetching data from {payload['start_time']} to {payload['end_time']}")

        cookies = {"token": token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                f"{BASE_URL}/edge/data",
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=300
            )
        except requests.exceptions.RequestException:
            print(f"Connection error for {payload['start_time']}, skipping...")
            current_start = current_end
            continue

        if not response.ok:
            print(f"HTTP {response.status_code} for {payload['start_time']}, skipping...")
            current_start = current_end
            continue

        try:
            records = response.json()
        except json.JSONDecodeError:
            print(f"Failed to parse JSON for {payload['start_time']}, skipping...")
            current_start = current_end
            continue

        if not isinstance(records, list) or len(records) == 0:
            print(f"No data for {payload['start_time']}, skipping...")
            current_start = current_end
            continue

        device_features = defaultdict(list)
        for record in records:
            device_alias = record.get("device_alias", "").strip()
            if not device_alias or device_alias.lower() == "unknown":
                continue

            feature = {
                "type": "Feature",
                "properties": {
                    key: value for key, value in record.items() if key != "data"
                }
            }

            if isinstance(record.get("data"), dict):
                for k, v in record["data"].items():
                    if isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            feature["properties"][f"{k}_{sub_k}"] = sub_v
                    else:
                        feature["properties"][k] = v

            device_features[device_alias].append(feature)

        for device_alias, features in device_features.items():
            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            filename = f"sensor{device_alias}_{current_start.strftime('%Y-%m-%d')}.geojson"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(geojson, f, indent=2)

            print(f"Saved file: {filename}")
            upload_to_s3(filename, bucket)

        current_start = current_end

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

with DAG(
    dag_id="bp3d_upload_to_s3",
    description="Fetch BurnPro3D edge data and upload to S3",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    default_args=default_args,
) as dag:
    fetch_and_upload_task = PythonOperator(
        task_id="bp3d_upload_to_s3",
        python_callable=fetch_bp3d_sensor_data
    )
