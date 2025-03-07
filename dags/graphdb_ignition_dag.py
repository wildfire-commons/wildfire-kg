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

    # Print environment variables
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

    # GraphDB connection details
    GRAPHDB_URL = "http://host.docker.internal:7200"
    REPOSITORY = "wildfire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

    # Test connection
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

    print("Starting data import...")
    try:
        # List objects in bucket to find the correct path
        s3_objects = s3_client.list_objects_v2(
            Bucket=aws_s3_bucket_name,
            Prefix='undefined/'  # Changed from 'sensors/' to 'undefined/'
        )
        
        print("Available files in S3:")
        for obj in s3_objects.get('Contents', []):
            print(f"- {obj['Key']}")

        # Get file from S3 with correct path
        s3_response = s3_client.get_object(
            Bucket=aws_s3_bucket_name,
            Key='undefined/sensorRLS6.geojson'  # Updated path to match URL structure
        )
        
        # Read GeoJSON from S3
        geojson_data = json.loads(s3_response['Body'].read().decode('utf-8'))
        features = geojson_data.get("features", [])
        
        if not features:
            raise ValueError("No sensor data found in dataset.")

        # Process features to match schema
        data = []
        for f in features:
            if "properties" in f and "geometry" in f:
                sensor_data = {
                    "db_id": f["properties"]["id"],
                    "time": f["properties"]["time"],
                    "longitude": f["geometry"]["coordinates"][0],
                    "latitude": f["geometry"]["coordinates"][1],
                    "temperatureMillidegreeC": f["properties"]["temperatureMillidegreeC"],
                    "barometricPa": f["properties"]["barometricPa"],
                    "humidityRh": f["properties"]["humidityRh"],
                    "CO2Ppm": f["properties"]["CO2Ppm"],
                    "mos_gasResistance": f["properties"]["mos_gasResistance"]
                }
                data.append(sensor_data)

        print(f"Processing {len(data)} sensor readings")

        # Load to GraphDB following schema
        for sensor in data:
            sensor_id = str(sensor['db_id'])
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            INSERT DATA {{ 
                GRAPH <http://wifire.ucsd.edu/sensor_data> {{
                    # Main FireIgnitionSensor instance
                    wifire:sensor_{sensor_id} rdf:type wifire:FireIgnitionSensor .
                    
                    # SensorMetadata
                    wifire:metadata_{sensor_id} rdf:type wifire:SensorMetadata ;
                        wifire:db_id "{sensor_id}"^^xsd:integer ;
                        wifire:model_type "RLS6" ;
                        wifire:time "{sensor['time']}"^^xsd:dateTime ;
                        wifire:device_alias "RLS6_Sensor" ;
                        wifire:sensor_type_id "1"^^xsd:integer .
                    
                    # Link to SensorMetadata
                    wifire:sensor_{sensor_id} wifire:hasSensorMetadata wifire:metadata_{sensor_id} .
                    
                    # LocationData
                    wifire:location_{sensor_id} rdf:type wifire:LocationData ;
                        wifire:longitude "{sensor['longitude']}"^^xsd:float ;
                        wifire:latitude "{sensor['latitude']}"^^xsd:float .
                    
                    # Link to LocationData
                    wifire:sensor_{sensor_id} wifire:hasLocationData wifire:location_{sensor_id} .
                    
                    # SensorTypeData
                    wifire:type_{sensor_id} rdf:type wifire:SensorTypeData ;
                        wifire:type "FireIgnition" .
                    
                    # Link to SensorTypeData
                    wifire:sensor_{sensor_id} wifire:hasSensorTypeData wifire:type_{sensor_id} .
                    
                    # EnvironmentalData
                    wifire:env_{sensor_id} rdf:type wifire:EnvironmentalData ;
                        wifire:temperatureMillidegreeC "{sensor['temperatureMillidegreeC']}"^^xsd:integer ;
                        wifire:barometricPa "{sensor['barometricPa']}"^^xsd:integer ;
                        wifire:humidityRh "{sensor['humidityRh']}"^^xsd:integer ;
                        wifire:CO2Ppm "{sensor['CO2Ppm']}"^^xsd:integer ;
                        wifire:mos_gasResistance "{sensor['mos_gasResistance']}"^^xsd:integer .
                    
                    # Link to EnvironmentalData
                    wifire:sensor_{sensor_id} wifire:hasEnvironmentalData wifire:env_{sensor_id} .
                    
                    # ParticleData
                    wifire:particle_{sensor_id} rdf:type wifire:ParticleData ;
                        wifire:pmsensor_pm10Standard "0"^^xsd:integer ;
                        wifire:pmsensor_pm25Standard "0"^^xsd:integer .
                    
                    # Link to ParticleData
                    wifire:sensor_{sensor_id} wifire:hasParticleData wifire:particle_{sensor_id} .
                    
                    # WindData
                    wifire:wind_{sensor_id} rdf:type wifire:WindData ;
                        wifire:wind_windDirectionDegrees "0"^^xsd:integer ;
                        wifire:wind_windSpeedCmS "0"^^xsd:integer .
                    
                    # Link to WindData
                    wifire:sensor_{sensor_id} wifire:hasWindData wifire:wind_{sensor_id} .
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
                print(f"Failed to add sensor {sensor_id}. Status: {response.status_code}")
                return
        
        print(f"Successfully loaded {len(data)} sensor readings to GraphDB")
            
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