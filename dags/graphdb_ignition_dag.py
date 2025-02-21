import urllib3
import requests
import json
import pandas as pd
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# local GraphDB connection details
GRAPHDB_URL = "http://localhost:7200"
REPOSITORY = "wildfire-kg"
SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
TIME = Namespace("http://www.w3.org/2006/time#")

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

def process_and_load_data(file_path):
    """Process and load sensor data into GraphDB"""
    print(f"Processing file: {file_path}")
    
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

        # load to GraphDB using direct SPARQL UPDATE
        for event in data_dict:
            ign_id = str(event['event_id'])
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX time: <http://www.w3.org/2006/time#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            INSERT DATA {{
                wifire:sensor_{ign_id} 
                    wifire:hasID "{ign_id}" ;
                    wifire:hasLocation wifire:loc_{ign_id} ;
                    time:hasTime "{event['timestamp'].isoformat()}"^^xsd:dateTime ;
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
                print(f"Response: {response.text}")
                return False
            
        print(f"Successfully loaded {len(data_dict)} events to GraphDB")
        return True
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        return False

def verify_data():
    verify_query = """
    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
    SELECT (COUNT(*) as ?count) 
    WHERE { 
        ?s wifire:type wifire:SensorReading .
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
            print(f"Found {count} sensor readings in GraphDB")
            
            # sample query
            sample_query = """
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            SELECT ?id ?time ?temp ?co2 ?humidity
            WHERE { 
                ?s wifire:type wifire:SensorReading ;
                   wifire:hasID ?id ;
                   time:hasTime ?time ;
                   wifire:temperature ?temp ;
                   wifire:CO2 ?co2 ;
                   wifire:humidity ?humidity .
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
                print("\nSample of sensor readings:")
                for binding in sample_results['results']['bindings']:
                    print(f"ID: {binding['id']['value']}")
                    print(f"Time: {binding['time']['value']}")
                    print(f"Temperature: {binding['temp']['value']} mC")
                    print(f"CO2: {binding['co2']['value']} ppm")
                    print(f"Humidity: {binding['humidity']['value']} RH")
                    print("---")
            
            return True
        else:
            print(f"Failed to verify data. Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error verifying data: {str(e)}")
        return False

if __name__ == "__main__":
    print("Starting data import test...")
    if verify_repository():
        file_path = "../data/raw/sensorRLS6.geojson"
        if process_and_load_data(file_path):
            verify_data()
    print("Test completed.") 