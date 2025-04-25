from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from datetime import datetime
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

def process_and_load_data():
    # Move imports inside
    import pandas as pd
    import requests
    import urllib3
    import boto3
    import io
    import json
    from rdflib import Graph, Namespace, Literal, URIRef
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Get credentials from Airflow Variables
    aws_access_key_id = Variable.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = Variable.get("AWS_SECRET_ACCESS_KEY")
    aws_s3_endpoint_url = Variable.get("AWS_S3_ENDPOINT_URL")
    aws_s3_bucket_name = Variable.get("AWS_S3_BUCKET_NAME")

    # Print environment variables to debug
    print("Environment variables:")
    print(f"AWS_ACCESS_KEY_ID: {'*' * len(aws_access_key_id) if aws_access_key_id else 'Not set'}")
    print(f"AWS_SECRET_ACCESS_KEY: {'*' * 5 if aws_secret_access_key else 'Not set'}")
    print(f"AWS_S3_ENDPOINT_URL: {aws_s3_endpoint_url}")
    print(f"AWS_S3_BUCKET_NAME: {aws_s3_bucket_name}")

    # Set up S3 client
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=aws_s3_endpoint_url,
        verify=False
    )

    # local GraphDB connection details
    GRAPHDB_URL = "http://host.docker.internal:7200"
    REPOSITORY = "wildfire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

    # Test GraphDB connection
    try:
        test_response = requests.get(
            SPARQL_ENDPOINT,
            params={'query': 'ASK { ?s ?p ?o }'},
            headers={'Accept': 'application/sparql-results+json'},
            verify=False
        )
        print(f"GraphDB connection test status: {test_response.status_code}")
        if test_response.status_code != 200:
            raise Exception(f"GraphDB connection failed with status {test_response.status_code}")
    except Exception as e:
        print(f"Error connecting to GraphDB: {str(e)}")
        raise

    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")

    def transform_feature(feature):
        """Transform feature to match expected format"""
        props = feature.get('properties', {})
        
        # Extract coordinates from geometry if available, otherwise from properties
        coords = None
        if feature.get('geometry') and feature['geometry'].get('coordinates'):
            coords = feature['geometry']['coordinates']
        elif props.get('geom') and 'POINT EMPTY' not in props['geom']:
            # Parse "POINT (-119.7992225 34.4344215)" format
            coords_str = props['geom'].replace('POINT (', '').replace(')', '')
            coords = [float(x) for x in coords_str.split()]
            
        if not coords:
            return None
            
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": coords
            },
            "properties": {
                "id": props.get('id'),
                "time": props.get('time'),
                "device_alias": props.get('device_alias'),
                "temperatureMillidegreeC": props.get('temperatureMillidegreeC'),
                "barometricPa": props.get('barometricPa'),
                "humidityRh": props.get('humidityRh'),
                "longitude": coords[0],
                "latitude": coords[1]
            }
        }

    print("Starting data import...")
    try:
        # List objects in bucket
        response = s3_client.list_objects_v2(Bucket=aws_s3_bucket_name)
        print("S3 response:", response)
        
        # Process each sensor file
        for obj in response.get('Contents', []):
            if obj['Key'].startswith('sensor') and obj['Key'].endswith('.geojson'):
                print(f"\nProcessing file: {obj['Key']}")
                try:
                    # Get file from S3
                    s3_response = s3_client.get_object(
                        Bucket=aws_s3_bucket_name,
                        Key=obj['Key']
                    )
                    
                    # Read and parse the JSON data
                    data = json.loads(s3_response['Body'].read().decode('utf-8'))
                    print(f"Successfully read file: {obj['Key']}")
                    print(f"Number of features: {len(data.get('features', []))}")
                    
                    # Transform features
                    transformed_features = []
                    for feature in data.get('features', []):
                        transformed = transform_feature(feature)
                        if transformed:
                            transformed_features.append(transformed)
                    
                    print(f"Transformed {len(transformed_features)} features from {obj['Key']}")
                    
                    # Process each transformed feature
                    for feature in transformed_features:
                        props = feature['properties']
                        coords = feature['geometry']['coordinates']
                        
                        # Create SPARQL update query
                        update_query = f"""
                        PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                        
                        INSERT DATA {{ 
                            GRAPH <http://wifire.ucsd.edu/sensor_readings> {{
                                wifire:reading_{props['id']} rdf:type wifire:SensorReading ;
                                    wifire:hasTime "{props['time']}"^^xsd:dateTime ;
                                    wifire:hasDevice "{props['device_alias']}"^^xsd:string ;
                                    wifire:hasTemperature "{props['temperatureMillidegreeC']}"^^xsd:integer ;
                                    wifire:hasBarometricPressure "{props['barometricPa']}"^^xsd:integer ;
                                    wifire:hasHumidity "{props['humidityRh']}"^^xsd:integer ;
                                    wifire:hasLongitude "{coords[0]}"^^xsd:float ;
                                    wifire:hasLatitude "{coords[1]}"^^xsd:float .
                            }}
                        }}
                        """
                        
                        headers = {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Accept': '*/*'
                        }
                        
                        response = requests.post(
                            UPDATE_ENDPOINT,
                            data={'update': update_query},
                            headers=headers,
                            verify=False
                        )
                        
                        if response.status_code not in [200, 204]:
                            print(f"Failed to add reading {props['id']}. Status: {response.status_code}")
                            continue
                    
                    print(f"Successfully uploaded {len(transformed_features)} readings from {obj['Key']}")
                    
                except Exception as file_error:
                    print(f"Error processing file {obj['Key']}: {str(file_error)}")
                    continue

    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        raise

with DAG(
    'graphdb_ignition_import',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='Import ignition sensor data into GraphDB'
) as dag:
    
    install_deps = BashOperator(
        task_id='install_dependencies',
        bash_command='pip install --no-cache-dir rdflib requests pandas boto3',
    )
    
    load_data = PythonOperator(
        task_id='process_and_load_data',
        python_callable=process_and_load_data
    )
    
    install_deps >> load_data 