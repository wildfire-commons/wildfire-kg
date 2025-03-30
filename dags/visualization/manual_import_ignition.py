import urllib3
import requests
import json
import pandas as pd
import boto3
import io
from rdflib import Graph, Namespace, Literal, URIRef
from dotenv import load_dotenv
import os
from tqdm import tqdm
import time

# Load environment variables
load_dotenv()

# Get S3 credentials from environment
aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_s3_endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL")
aws_s3_bucket_name = os.getenv("AWS_S3_BUCKET_NAME")

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# GraphDB connection details
GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
REPOSITORY = "wildfire-kg"
UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

# Define namespaces
WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
TIME = Namespace("http://www.w3.org/2006/time#")

def process_and_load_data():
    # Set up S3 client
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=aws_s3_endpoint_url,
        verify=False
    )
    
    print("Starting data import...")
    try:
        # List objects in bucket with .geojson extension
        s3_objects = s3_client.list_objects_v2(
            Bucket=aws_s3_bucket_name,
            Prefix='undefined/'
        )
        
        # Filter for .geojson files
        geojson_files = [
            obj['Key'] for obj in s3_objects.get('Contents', [])
            if obj['Key'].endswith('.geojson')
        ]
        
        print("\nAvailable GeoJSON files in S3:")
        for file_key in geojson_files:
            print(f"- {file_key}")

        total_sensors = 0
        start_time = time.time()
        
        # Process each GeoJSON file with progress bar
        for file_key in tqdm(geojson_files, desc="Processing files", unit="file"):
            # Get file from S3
            s3_response = s3_client.get_object(
                Bucket=aws_s3_bucket_name,
                Key=file_key
            )
            
            # Read GeoJSON from S3
            geojson_data = json.loads(s3_response['Body'].read().decode('utf-8'))
            features = geojson_data.get("features", [])
            
            if not features:
                print(f"\nNo sensor data found in {file_key}")
                continue

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

            print(f"\nUploading {len(data)} sensors from {file_key}")
            
            # Upload sensors with progress bar
            for sensor in tqdm(data, desc="Uploading sensors", unit="sensor"):
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
                    print(f"\nFailed to add sensor {sensor_id}. Status: {response.status_code}")
                    print(f"Response: {response.text}")
                    return
                
                total_sensors += 1
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\nImport completed:")
        print(f"Total sensors processed: {total_sensors}")
        print(f"Total time: {duration:.2f} seconds")
        print(f"Average time per sensor: {(duration/total_sensors):.2f} seconds")
            
    except Exception as e:
        print(f"\nError processing and loading data: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    process_and_load_data() 