from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime

def process_and_load_data():
    # Move imports inside
    import urllib3
    import requests
    import json
    import pandas as pd
    from rdflib import Graph, Namespace, Literal, URIRef
    from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # local GraphDB connection details
    GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
    REPOSITORY = "wildfire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")

    # Your existing functions
    file_path = "/opt/airflow/dags/data/raw/sensorRLS6.geojson"
    
    print("Starting data import...")
    try:
        # load and process the data
        with open(file_path, 'r') as f:
            geojson_data = json.load(f)

        features = geojson_data.get("features", [])
        if not features:
            raise ValueError("No ignition events found in dataset.")

        data = [
            {
                **f["properties"],
                "longitude": f["geometry"]["coordinates"][0],
                "latitude": f["geometry"]["coordinates"][1]
            }
            for f in features if "properties" in f and "geometry" in f
        ]

        df = pd.DataFrame(data)
        processed_data = df[['id', 'time', 'longitude', 'latitude', 'temperatureMillidegreeC',
                            'barometricPa', 'humidityRh', 'CO2Ppm', 'mos_gasResistance']].copy()

        processed_data = processed_data.astype({
            'id': int,                         
            'temperatureMillidegreeC': float,  
            'barometricPa': float,             
            'humidityRh': float,               
            'CO2Ppm': float,                   
            'mos_gasResistance': float,        
            'longitude': float,
            'latitude': float
        })

        processed_data.rename(columns={
            'id': 'event_id',
            'time': 'timestamp',
            'temperatureMillidegreeC': 'temperature_mC',
            'barometricPa': 'pressure_Pa',
            'humidityRh': 'humidity_RH',
            'CO2Ppm': 'CO2_ppm',
            'mos_gasResistance': 'gas_resistance'
        }, inplace=True)

        processed_data['timestamp'] = pd.to_datetime(processed_data['timestamp'])
        data_dict = processed_data.to_dict(orient='records')
        
        print(f"Processed {len(data_dict)} records")

        # load to GraphDB
        for event in data_dict:
            ign_id = str(event['event_id'])
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            INSERT {{ 
                GRAPH <http://wifire.ucsd.edu/ignition> {{
                    wifire:sensor_{ign_id} 
                        wifire:hasID "{ign_id}" ;
                        wifire:hasLocation wifire:loc_{ign_id} ;
                        wifire:hasTime "{event['timestamp'].isoformat()}"^^xsd:dateTime ;
                        wifire:type wifire:SensorReading ;
                        wifire:temperature "{event['temperature_mC']}"^^xsd:float ;
                        wifire:pressure "{event['pressure_Pa']}"^^xsd:float ;
                        wifire:humidity "{event['humidity_RH']}"^^xsd:float ;
                        wifire:CO2 "{event['CO2_ppm']}"^^xsd:float ;
                        wifire:gasResistance "{event['gas_resistance']}"^^xsd:float .
                        
                    wifire:loc_{ign_id} 
                        wifire:type geo:Feature ;
                        wifire:longitude "{event['longitude']}"^^xsd:float ;
                        wifire:latitude "{event['latitude']}"^^xsd:float .
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
                print(f"Failed to add event {ign_id}. Status: {response.status_code}")
                return
        
        print(f"Successfully loaded {len(data_dict)} events to GraphDB")
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")

with DAG(
    'graphdb_ignition_import',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='Import ignition data into GraphDB'
) as dag:
    
    install_deps = BashOperator(
        task_id='install_dependencies',
        bash_command='pip install --no-cache-dir rdflib requests pandas',
    )
    
    load_data = PythonOperator(
        task_id='process_and_load_data',
        python_callable=process_and_load_data,
    )
    
    install_deps >> load_data 