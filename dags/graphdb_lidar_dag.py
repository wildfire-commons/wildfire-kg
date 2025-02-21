import urllib3
import requests
import json
import pandas as pd
import numpy as np
import laspy
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GRAPHDB_URL = "http://localhost:7200"
REPOSITORY = "wildfire-kg"
SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
TIME = Namespace("http://www.w3.org/2006/time#")

def verify_repository():
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

def process_and_load_data(file_path):
    print(f"Processing file: {file_path}")
    
    try:
        las = laspy.read(file_path)
        
        # extract point cloud data
        pointcloud_df = pd.DataFrame({
            'x': np.array(las.x),
            'y': np.array(las.y),
            'z': np.array(las.z),
            'intensity': np.array(las.intensity),
            'classification': np.array(las.classification),
            'return_number': np.array(las.return_number),
            'number_of_returns': np.array(las.number_of_returns),
            'scan_angle_rank': np.array(las.scan_angle_rank),
            'point_source_id': np.array(las.point_source_id)
        })
        
        # convert types 
        pointcloud_df = pointcloud_df.astype({
            'x': float,
            'y': float,
            'z': float,
            'intensity': float,
            'classification': int,
            'return_number': int,
            'number_of_returns': int,
            'scan_angle_rank': int,
            'point_source_id': int
        })
        
        timestamp = datetime.now()
        
        # process in chunks
        chunk_size = 1000
        total_points = len(pointcloud_df)
        chunks = [np.array_split(pointcloud_df, np.ceil(total_points/chunk_size))[0]]  # testing with first chunk
        print(f"Processing {total_points} points in {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks):
            chunk_dict = chunk.to_dict(orient='records')
            
            for j, point in enumerate(chunk_dict):
                point_id = f"point_{format(point['x'], '.2f')}_{format(point['y'], '.2f')}" 
                
                update_query = f"""
                PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                PREFIX geo: <http://www.opengis.net/ont/geosparql#>
                PREFIX time: <http://www.w3.org/2006/time#>
                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                
                INSERT DATA {{
                    wifire:point_{point_id} 
                        wifire:hasID "{point_id}" ;
                        wifire:hasLocation wifire:loc_{point_id} ;
                        time:hasTime "{timestamp.isoformat()}"^^xsd:dateTime ;
                        wifire:type wifire:LiDARPoint ;
                        wifire:intensity "{format(float(point['intensity']), '.6f')}"^^xsd:float ;
                        wifire:classification "{int(point['classification'])}"^^xsd:integer ;
                        wifire:returnNumber "{int(point['return_number'])}"^^xsd:integer ;
                        wifire:numberOfReturns "{int(point['number_of_returns'])}"^^xsd:integer ;
                        wifire:scanAngleRank "{int(point['scan_angle_rank'])}"^^xsd:integer ;
                        wifire:pointSourceId "{int(point['point_source_id'])}"^^xsd:integer .
                        
                    wifire:loc_{point_id} 
                        wifire:type geo:Feature ;
                        wifire:x "{format(float(point['x']), '.6f')}"^^xsd:float ;
                        wifire:y "{format(float(point['y']), '.6f')}"^^xsd:float ;
                        wifire:z "{format(float(point['z']), '.6f')}"^^xsd:float .
                }}
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
            
        print(f"Successfully loaded {total_points} points to GraphDB")
        return True
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        return False

def verify_data():
    """Verify the loaded data"""
    verify_query = """
    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
    SELECT (COUNT(*) as ?count) 
    WHERE { 
        ?s wifire:type wifire:LiDARPoint .
    }
    """
    
    try:
        response = requests.get(
            SPARQL_ENDPOINT,
            params={'query': verify_query},
            headers={'Accept': 'application/sparql-results+json'}
        )
        
        if response.status_code == 200:
            results = response.json()
            count = results['results']['bindings'][0]['count']['value']
            print(f"Found {count} LiDAR points in GraphDB")
            
            # sample query
            sample_query = """
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            SELECT ?id ?x ?y ?z ?intensity ?class
            WHERE { 
                ?s wifire:type wifire:LiDARPoint ;
                   wifire:hasID ?id ;
                   wifire:hasLocation ?loc ;
                   wifire:intensity ?intensity ;
                   wifire:classification ?class .
                ?loc wifire:x ?x ;
                     wifire:y ?y ;
                     wifire:z ?z .
            }
            LIMIT 5
            """
            
            sample_response = requests.get(
                SPARQL_ENDPOINT,
                params={'query': sample_query},
                headers={'Accept': 'application/sparql-results+json'}
            )
            
            if sample_response.status_code == 200:
                sample_results = sample_response.json()
                print("\nSample of LiDAR points:")
                for binding in sample_results['results']['bindings']:
                    print(f"ID: {binding['id']['value']}")
                    print(f"Position: ({binding['x']['value']}, {binding['y']['value']}, {binding['z']['value']})")
                    print(f"Intensity: {binding['intensity']['value']}")
                    print(f"Classification: {binding['class']['value']}")
                    print("---")
            
            return True
        else:
            print(f"Failed to verify data. Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error verifying data: {str(e)}")
        return False

if __name__ == "__main__":
    print("Starting LiDAR data import test...")
    if verify_repository():
        file_path = "../data/raw/CA_SoCal_Wildfires_B4_2018_Sedgwick_TREX24_1.laz" # test with aerial data
        if process_and_load_data(file_path):
            verify_data()
    print("Test completed.") 