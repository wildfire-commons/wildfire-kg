from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from datetime import datetime
import os
import time
from dotenv import load_dotenv

# Load .env file
load_dotenv()

def process_and_load_data():
    # Move imports inside
    import pandas as pd
    import requests
    import urllib3
    import boto3
    from botocore.config import Config
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

    # Set up S3 client with retry configuration
    s3_config = Config(
        retries=dict(
            max_attempts=5,
            mode='adaptive'
        )
    )
    
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=aws_s3_endpoint_url,
        verify=False,
        config=s3_config
    )

    # local GraphDB connection details
    GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
    REPOSITORY = "wildfire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

    # Set up requests session with retry configuration
    session = requests.Session()
    retry = urllib3.Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    # Test GraphDB connection
    try:
        test_response = session.get(
            SPARQL_ENDPOINT,
            params={'query': 'ASK { ?s ?p ?o }'},
            headers={'Accept': 'application/sparql-results+json'},
            verify=False,
            timeout=30
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
                "longitudeSensor": coords[0],
                "latitudeSensor": coords[1],
                "provider": props.get('provider', 'Unknown')
            }
        }

    print("Starting data import...")
    try:
        # List objects in bucket
        print("Available files in S3:")
        paginator = s3_client.get_paginator('list_objects_v2')
        file_count = 0
        total_files = 0
        
        # First pass to count total files
        for page in paginator.paginate(Bucket=aws_s3_bucket_name):
            for obj in page.get('Contents', []):
                if obj['Key'].startswith('sensor') and obj['Key'].endswith('.geojson'):
                    total_files += 1
        
        print(f"\nFound {total_files} sensor files to process")
        
        # Second pass to process files
        for page in paginator.paginate(Bucket=aws_s3_bucket_name):
            for obj in page.get('Contents', []):
                if obj['Key'].startswith('sensor') and obj['Key'].endswith('.geojson'):
                    file_count += 1
                    print(f"\nProcessing file {file_count}/{total_files}: {obj['Key']}")
                    try:
                        # Get file from S3
                        s3_response = s3_client.get_object(
                            Bucket=aws_s3_bucket_name,
                            Key=obj['Key']
                        )
                        
                        # Read and parse the JSON data
                        data = json.loads(s3_response['Body'].read().decode('utf-8'))
                        total_features = len(data.get('features', []))
                        print(f"Successfully read file: {obj['Key']}")
                        print(f"Number of features: {total_features}")
                        
                        # Transform features
                        transformed_features = []
                        skipped_features = 0
                        for feature in data.get('features', []):
                            transformed = transform_feature(feature)
                            if transformed:
                                transformed_features.append(transformed)
                            else:
                                skipped_features += 1
                        
                        print(f"Transformed {len(transformed_features)} features from {obj['Key']}")
                        if skipped_features > 0:
                            print(f"Skipped {skipped_features} features due to missing or invalid coordinates")
                        
                        if not transformed_features:
                            print(f"No valid features found in {obj['Key']}, skipping...")
                            continue

                        # Process transformed features in batches
                        BATCH_SIZE = 200
                        total_features = len(transformed_features)
                        successful_uploads = 0
                        failed_uploads = 0

                        for i in range(0, total_features, BATCH_SIZE):
                            batch = transformed_features[i:i + BATCH_SIZE]
                            batch_queries = []
                            
                            for feature in batch:
                                props = feature['properties']
                                coords = feature['geometry']['coordinates']
                                
                                # Create SPARQL update query
                                update_query = f"""
                                PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                                PREFIX geo: <http://www.opengis.net/ont/geosparql#>
                                PREFIX time: <http://www.w3.org/2006/time#>
                                
                                INSERT DATA {{ 
                                    GRAPH <http://wifire.ucsd.edu/sensor_readings_location> {{
                                        # Main FireIgnitionSensor instance
                                        wifire:sensor_{props['id']} rdf:type wifire:FireIgnitionSensor ;
                                            rdfs:label "Fire Ignition Sensor" ;
                                            rdfs:comment "Represents a sensor used for detecting fire ignition points" .
                                        
                                        # SensorMetadata with additional properties
                                        wifire:metadata_{props['id']} rdf:type wifire:SensorMetadata ;
                                            rdfs:label "Sensor Metadata" ;
                                            rdfs:comment "Metadata related to the FireIgnitionSensor" ;
                                            wifire:device_alias "{props['device_alias']}"^^xsd:string ;
                                            wifire:time "{props['time']}"^^xsd:dateTime ;
                                            wifire:db_id "{props['id']}"^^xsd:int ;
                                            wifire:model_type "{props.get('model_type', 'unknown')}"^^xsd:string ;
                                            wifire:db_urn "{props.get('db_urn', '')}"^^xsd:string ;
                                            wifire:sensor_type_id "{props.get('sensor_type_id', '0')}"^^xsd:int ;
                                            wifire:provider "{props.get('provider', 'Unknown')}"^^xsd:string .
                                        
                                        # Link FireIgnitionSensor to SensorMetadata
                                        wifire:sensor_{props['id']} wifire:hasSensorMetadata wifire:metadata_{props['id']} .
                                        
                                        # LocationDataSensor
                                        wifire:location_{props['id']} rdf:type wifire:LocationDataSensor ;
                                            rdfs:label "Location Data Sensor" ;
                                            rdfs:comment "Represents the geographical location of the FireIgnitionSensor" ;
                                            wifire:longitudeSensor "{coords[0]}"^^xsd:float ;
                                            wifire:latitudeSensor "{coords[1]}"^^xsd:float .
                                        
                                        # Link FireIgnitionSensor to LocationDataSensor
                                        wifire:sensor_{props['id']} wifire:hasLocationDataSensor wifire:location_{props['id']} .
                                        
                                        # SensorTypeData
                                        wifire:type_{props['id']} rdf:type wifire:SensorTypeData ;
                                            rdfs:label "Sensor Type Data" ;
                                            rdfs:comment "Represents data related to the type of fire sensor" ;
                                            wifire:type "{props.get('sensor_type', 'unknown')}"^^xsd:string .
                                        
                                        # Link FireIgnitionSensor to SensorTypeData
                                        wifire:sensor_{props['id']} wifire:hasSensorTypeData wifire:type_{props['id']} .
                                        
                                        # EnvironmentalData with additional properties
                                        wifire:env_{props['id']} rdf:type wifire:EnvironmentalData ;
                                            rdfs:label "Environmental Data" ;
                                            rdfs:comment "Represents environmental data collected by the sensor" ;
                                            wifire:temperatureMillidegreeC "{props['temperatureMillidegreeC']}"^^xsd:integer ;
                                            wifire:barometricPa "{props['barometricPa']}"^^xsd:integer ;
                                            wifire:humidityRh "{props['humidityRh']}"^^xsd:integer ;
                                            wifire:CO2Ppm "{props.get('CO2Ppm', '0')}"^^xsd:integer ;
                                            wifire:mos_gasResistance "{props.get('mos_gasResistance', '0')}"^^xsd:integer .
                                        
                                        # Link FireIgnitionSensor to EnvironmentalData
                                        wifire:sensor_{props['id']} wifire:hasEnvironmentalData wifire:env_{props['id']} .
                                        
                                        # ParticleData
                                        wifire:particle_{props['id']} rdf:type wifire:ParticleData ;
                                            rdfs:label "Particle Data" ;
                                            rdfs:comment "Represents particle data, such as particle density and size" ;
                                            wifire:pmsensor_pm10Standard "{props.get('pmsensor_pm10Standard', '0')}"^^xsd:integer ;
                                            wifire:pmsensor_pm25Standard "{props.get('pmsensor_pm25Standard', '0')}"^^xsd:integer .
                                        
                                        # Link FireIgnitionSensor to ParticleData
                                        wifire:sensor_{props['id']} wifire:hasParticleData wifire:particle_{props['id']} .
                                        
                                        # WindData
                                        wifire:wind_{props['id']} rdf:type wifire:WindData ;
                                            rdfs:label "Wind Data" ;
                                            rdfs:comment "Represents wind speed and direction data collected by the sensor" ;
                                            wifire:wind_windDirectionDegrees "{props.get('wind_windDirectionDegrees', '0')}"^^xsd:integer ;
                                            wifire:wind_windSpeedCmS "{props.get('wind_windSpeedCmS', '0')}"^^xsd:integer .
                                        
                                        # Link FireIgnitionSensor to WindData
                                        wifire:sensor_{props['id']} wifire:hasWindData wifire:wind_{props['id']} .
                                    }}
                                }}
                                """
                                batch_queries.append(update_query)
                            
                            # Execute batch update with retry
                            max_retries = 3
                            for attempt in range(max_retries):
                                try:
                                    # Join queries with semicolons to properly terminate each query
                                    combined_query = ';\n'.join(batch_queries) + ';'
                                    response = session.post(
                                        UPDATE_ENDPOINT,
                                        data={'update': combined_query},
                                        headers={'Content-Type': 'application/x-www-form-urlencoded'},
                                        verify=False,
                                        timeout=60
                                    )
                                    
                                    if response.status_code in [200, 204]:
                                        successful_uploads += len(batch)
                                        print(f"✓ Successfully uploaded batch {i//BATCH_SIZE + 1} of {(total_features + BATCH_SIZE - 1)//BATCH_SIZE}")
                                        break
                                    else:
                                        if attempt == max_retries - 1:
                                            print(f"✗ Failed to upload batch {i//BATCH_SIZE + 1}. Status: {response.status_code}")
                                            print(f"Response: {response.text}")
                                            failed_uploads += len(batch)
                                        else:
                                            print(f"Retry {attempt + 1}/{max_retries} for batch {i//BATCH_SIZE + 1}")
                                            time.sleep(2 ** attempt)  # Exponential backoff
                                except Exception as e:
                                    if attempt == max_retries - 1:
                                        print(f"✗ Error uploading batch {i//BATCH_SIZE + 1}: {str(e)}")
                                        failed_uploads += len(batch)
                                    else:
                                        print(f"Retry {attempt + 1}/{max_retries} for batch {i//BATCH_SIZE + 1}: {str(e)}")
                                        time.sleep(2 ** attempt)  # Exponential backoff
                            
                            # Add a small delay between batches to prevent overwhelming the server
                            if i + BATCH_SIZE < total_features:
                                time.sleep(1)
                        
                        print(f"\nUpload summary for {obj['Key']}:")
                        print(f"- Successfully uploaded: {successful_uploads}")
                        print(f"- Failed uploads: {failed_uploads}")
                        print(f"- Total features processed: {total_features}")
                        
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