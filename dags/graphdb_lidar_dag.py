import urllib3
import requests
import json
import pandas as pd
import numpy as np
import laspy
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from datetime import datetime
import os
import glob

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GRAPHDB_URL = "http://localhost:7200"
REPOSITORY = "wildfire-kg"
SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
TIME = Namespace("http://www.w3.org/2006/time#")

def process_and_load_data(file_path, data_type):
    """Process and load LiDAR data into GraphDB"""
    print(f"Processing {data_type} LiDAR file: {file_path}")
    
    try:
        las = laspy.read(file_path)
        
        # Create base DataFrame with common attributes
        point_data = {
            'x': np.array(las.x),
            'y': np.array(las.y),
            'z': np.array(las.z),
            'intensity': np.array(las.intensity),
            'classification': np.array(las.classification),
            'return_number': np.array(las.return_number),
            'number_of_returns': np.array(las.number_of_returns),
            'point_source_id': np.array(las.point_source_id)
        }
        
        # Add scan_angle_rank only if it exists (aerial data)
        if hasattr(las, 'scan_angle_rank'):
            point_data['scan_angle_rank'] = np.array(las.scan_angle_rank)
        
        pointcloud_df = pd.DataFrame(point_data)
        
        # convert types
        type_conversions = {
            'x': float,
            'y': float,
            'z': float,
            'intensity': float,
            'classification': int,
            'return_number': int,
            'number_of_returns': int,
            'point_source_id': int
        }
        if 'scan_angle_rank' in pointcloud_df.columns:
            type_conversions['scan_angle_rank'] = int
            
        pointcloud_df = pointcloud_df.astype(type_conversions)
        
        timestamp = datetime.now()
        
        chunk_size = 1000
        total_points = len(pointcloud_df)
        chunks = [np.array_split(pointcloud_df, np.ceil(total_points/chunk_size))[0]]  # testing with first chunk
        #print(f"Processing {total_points} points in {len(chunks)} chunks") # inaccurate only one chunk right now
        
        for i, chunk in enumerate(chunks):
            chunk_dict = chunk.to_dict(orient='records')
            print(f"Processing {len(chunk_dict)} points in chunk {i+1}")

            for j, point in enumerate(chunk_dict):
                point_id = f"{data_type}_{format(point['x'], '.2f')}_{format(point['y'], '.2f')}"
            
                properties = [
                    f'wifire:hasID "{point_id}" ;',
                    f'wifire:hasLocation wifire:loc_{point_id} ;',
                    f'wifire:source "{data_type}" ;',
                    f'wifire:hasTime "{timestamp.isoformat()}"^^xsd:dateTime ;',
                    f'wifire:type wifire:{data_type.capitalize()}LiDARPoint ;',
                    f'wifire:intensity "{format(float(point["intensity"]), ".6f")}"^^xsd:float ;',
                    f'wifire:classification "{int(point["classification"])}"^^xsd:integer ;',
                    f'wifire:returnNumber "{int(point["return_number"])}"^^xsd:integer ;',
                    f'wifire:numberOfReturns "{int(point["number_of_returns"])}"^^xsd:integer ;',
                    f'wifire:pointSourceId "{int(point["point_source_id"])}"^^xsd:integer' 
                ]

                if 'scan_angle_rank' in point:
                    properties[-1] += ' ;'  # Add semicolon to previous last item
                    properties.append(f'wifire:scanAngleRank "{int(point["scan_angle_rank"])}"^^xsd:integer')
                
                # Join without adding extra semicolons
                properties_str = "\n                            ".join(properties)
                
                update_query = f"""
                PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                PREFIX geo: <http://www.opengis.net/ont/geosparql#>
                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                
                INSERT {{ 
                    GRAPH <http://wifire.ucsd.edu/lidar/{data_type}> {{
                        wifire:point_{point_id} 
                            wifire:hasID "{point_id}" ;
                            wifire:hasLocation wifire:loc_{point_id} ;
                            wifire:source "{data_type}" ;
                            wifire:hasTime "{timestamp.isoformat()}"^^xsd:dateTime ;
                            wifire:type wifire:{data_type.capitalize()}LiDARPoint ;
                            wifire:intensity "{format(float(point["intensity"]), ".6f")}"^^xsd:float ;
                            wifire:classification "{int(point["classification"])}"^^xsd:integer ;
                            wifire:returnNumber "{int(point["return_number"])}"^^xsd:integer ;
                            wifire:numberOfReturns "{int(point["number_of_returns"])}"^^xsd:integer ;
                            wifire:pointSourceId "{int(point["point_source_id"])}"^^xsd:integer {';' if 'scan_angle_rank' in point else '.'} 
                            {f'wifire:scanAngleRank "{int(point["scan_angle_rank"])}"^^xsd:integer .' if 'scan_angle_rank' in point else ''}
                            
                        wifire:loc_{point_id} 
                            wifire:type geo:Feature ;
                            wifire:x "{format(float(point['x']), '.6f')}"^^xsd:float ;
                            wifire:y "{format(float(point['y']), '.6f')}"^^xsd:float ;
                            wifire:z "{format(float(point['z']), '.6f')}"^^xsd:float .
                    }}
                }} WHERE {{}}
                """

                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': '*/*'
                }
                
                response = requests.post(
                    UPDATE_ENDPOINT,
                    data={'update': update_query},
                    headers=headers
                )
                
                if response.status_code not in [200, 204]:
                    print(f"Failed to add point {point_id}. Status: {response.status_code}")
                    print(f"Response: {response.text}")
                    return False
            
            if i % 10 == 0: 
                print(f"Processed chunk {i+1}/{len(chunks)}")
        
        #print(f"Successfully loaded {total_points} points to GraphDB") # inaccurate, only one chunk right now
        print(f"Successfully loaded points to GraphDB")

        return True
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        return False

def verify_repository():
    """Verify that the repository exists and is accessible"""
    print(f"Verifying repository: {REPOSITORY}")
    try:
        response = requests.get(
            SPARQL_ENDPOINT,
            params={'query': 'ASK { ?s ?p ?o }'},
            headers={'Accept': 'application/sparql-results+json'}
        )
        if response.status_code == 200:
            print(f"Successfully connected to repository '{REPOSITORY}'")
            return True
        else:
            print(f"Failed to connect to repository. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error verifying repository: {str(e)}")
        return False

def verify_data(data_type):
    """Verify the loaded data"""
    detail_query = f"""
    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
    
    SELECT DISTINCT ?p
    FROM <http://wifire.ucsd.edu/lidar/{data_type}>
    WHERE {{
        ?s ?p ?o .
    }}
    """
    
    try:
        response = requests.get(
            SPARQL_ENDPOINT,
            params={'query': detail_query},
            headers={'Accept': 'application/sparql-results+json'}
        )
        
        if response.status_code == 200:
            results = response.json()
            print(f"\nProperties in {data_type} graph:")
            for result in results['results']['bindings']:
                print(f"  {result['p']['value'].split('/')[-1]}")
            return True
        else:
            print(f"Failed to verify {data_type} data. Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error verifying {data_type} data: {str(e)}")
        return False

if __name__ == "__main__":
    print("Starting LiDAR data import test...")
    if verify_repository():
        # Process aerial data
        aerial_path = "../data/raw/aerial-lidar/*.laz"
        aerial_files = glob.glob(aerial_path)
        print(f"Found {len(aerial_files)} aerial LiDAR files")
        for file in aerial_files:
            if process_and_load_data(file, "aerial"):
                verify_data("aerial")
                
        # Process terrestrial data
        terrestrial_path = "../data/raw/terrestrial-lidar/*.laz"
        terrestrial_files = glob.glob(terrestrial_path)
        print(f"Found {len(terrestrial_files)} terrestrial LiDAR files")
        for file in terrestrial_files:
            if process_and_load_data(file, "terrestrial"):
                verify_data("terrestrial")
                
    print("Test completed.") 