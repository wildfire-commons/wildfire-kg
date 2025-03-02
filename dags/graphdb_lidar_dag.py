from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime

dag = DAG(
    'graphdb_lidar_import',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='Import LiDAR data into GraphDB'
)

def process_and_load_data():
    # Move all non-Airflow imports inside
    import laspy
    import numpy as np
    import pandas as pd
    import requests
    import urllib3
    from rdflib import Graph, Namespace, Literal, URIRef
    import glob
    from datetime import datetime
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
    REPOSITORY = "wildfire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"


    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")

    def process_lidar_file(file_path, data_type, chunk_size=1000, max_chunks=1):
        print(f"Processing {data_type} LiDAR file: {file_path}")
        try:
            las = laspy.read(file_path)
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
            
            if hasattr(las, 'scan_angle_rank'):
                point_data['scan_angle_rank'] = np.array(las.scan_angle_rank)
            
            df = pd.DataFrame(point_data)
            
            type_conversions = {
                'x': float, 'y': float, 'z': float,
                'intensity': float, 'classification': int,
                'return_number': int, 'number_of_returns': int,
                'point_source_id': int
            }
            if 'scan_angle_rank' in df.columns:
                type_conversions['scan_angle_rank'] = int
            
            df = df.astype(type_conversions)
            timestamp = datetime.now()
            
            chunks = np.array_split(df, np.ceil(len(df)/chunk_size))[:max_chunks]
            print(f"Processing first {max_chunks} chunks of size {chunk_size}")
            
            point_count = 0
            for i, chunk in enumerate(chunks):
                print(f"Processing chunk {i+1}/{len(chunks)} with {len(chunk)} points")
                chunk_dict = chunk.to_dict(orient='records')
                
                for point in chunk_dict:
                    point_id = f"{data_type}_{format(point['x'], '.2f')}_{format(point['y'], '.2f')}"
                    point_count += 1
                    
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
                                wifire:intensity "{format(float(point['intensity']), '.6f')}"^^xsd:float ;
                                wifire:classification "{int(point['classification'])}"^^xsd:integer ;
                                wifire:returnNumber "{int(point['return_number'])}"^^xsd:integer ;
                                wifire:numberOfReturns "{int(point['number_of_returns'])}"^^xsd:integer ;
                                wifire:pointSourceId "{int(point['point_source_id'])}"^^xsd:integer {';' if 'scan_angle_rank' in point else '.'} 
                                {f'wifire:scanAngleRank "{int(point["scan_angle_rank"])}"^^xsd:integer .' if 'scan_angle_rank' in point else ''}
                                
                            wifire:loc_{point_id} 
                                wifire:type geo:Feature ;
                                wifire:x "{format(float(point['x']), '.6f')}"^^xsd:float ;
                                wifire:y "{format(float(point['y']), '.6f')}"^^xsd:float ;
                                wifire:z "{format(float(point['z']), '.6f')}"^^xsd:float .
                        }}
                    }} WHERE {{}}
                    """
                    
                    response = requests.post(
                        UPDATE_ENDPOINT,
                        data={'update': update_query},
                        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': '*/*'}
                    )
                    
                    if response.status_code not in [200, 204]:
                        print(f"Failed to add point {point_id}. Status: {response.status_code}")
                        return False
                
                print(f"Successfully loaded {point_count} points from chunk {i+1}")
            
            print(f"Successfully loaded total {point_count} points from {file_path}")
            return True
            
        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")
            return False

    # Add connection test
    try:
        test_response = requests.get(
            SPARQL_ENDPOINT,
            params={'query': 'ASK { ?s ?p ?o }'},
            headers={'Accept': 'application/sparql-results+json'}
        )
        print(f"GraphDB connection test status: {test_response.status_code}")
        print(f"GraphDB response: {test_response.text}")
    except Exception as e:
        print(f"Error connecting to GraphDB: {str(e)}")

    # Process the files
    aerial_path = "/opt/airflow/dags/data/raw/aerial-lidar/*.laz"
    aerial_files = glob.glob(aerial_path)
    print(f"Found {len(aerial_files)} aerial LiDAR files")
    for file in aerial_files:
        process_lidar_file(file, "aerial")

    terrestrial_path = "/opt/airflow/dags/data/raw/terrestrial-lidar/*.laz"
    terrestrial_files = glob.glob(terrestrial_path)
    print(f"Found {len(terrestrial_files)} terrestrial LiDAR files")
    for file in terrestrial_files:
        process_lidar_file(file, "terrestrial")

# Tasks
install_deps = BashOperator(
    task_id='install_dependencies',
    bash_command='pip install --no-cache-dir laspy[lazrs] rdflib requests urllib3 numpy pandas',
    dag=dag
)

load_data = PythonOperator(
    task_id='process_and_load_data',
    python_callable=process_and_load_data,
    dag=dag
)

install_deps >> load_data 