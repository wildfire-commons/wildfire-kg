from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from datetime import datetime
import os
import time
from dotenv import load_dotenv
import pandas as pd
import numpy as np

def process_and_create_grouped_areas():
    from geopy.distance import geodesic
    import urllib3
    import requests
    import json
    from shapely.geometry import Point, Polygon
    from shapely import to_wkt
    from pyproj import Transformer
    from collections import defaultdict

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # GraphDB connection details
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

    REQUEST_TIMEOUT = 30
    MAX_RETRIES = 3
    GRID_SIZE = 200.0  # meters
    SENSOR_RADIUS = 2000.0  # meters (search radius for sensors near plot)

    def fetch_plot_metrics_data():
        query = """
        PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT ?plot ?plot_id ?lat ?lon
        WHERE {
            GRAPH <http://wifire.ucsd.edu/plot_metrics_temporal_geograph> {
                ?plot rdf:type wifire:PlotMetrics ;
                      wifire:hasLocationDataPlot ?loc .
                BIND(REPLACE(STR(?plot), "^.*plot_", "") AS ?plot_id)
                ?loc wifire:plotLatitude ?lat ;
                     wifire:plotLongitude ?lon .
            }
        }
        """
        headers = {'Accept': 'application/sparql-results+json'}
        for attempt in range(MAX_RETRIES):
            try:
                response = session.get(
                    SPARQL_ENDPOINT, 
                    params={'query': query}, 
                    headers=headers, 
                    verify=False,
                    timeout=REQUEST_TIMEOUT
                )
                if response.status_code == 200:
                    break
                print(f"Attempt {attempt + 1} failed with status {response.status_code}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)
            except requests.exceptions.Timeout:
                print(f"Timeout on attempt {attempt + 1}")
                if attempt == MAX_RETRIES - 1:
                    print("Failed to fetch plot data after all retries")
                    return []
                time.sleep(2)
            except requests.exceptions.RequestException as e:
                print(f"Error fetching plot data: {e}")
                return []
        
        results = response.json()['results']['bindings']
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32610", always_xy=True)
        plot_data = []
        for result in results:
            lon = float(result['lon']['value'])
            lat = float(result['lat']['value'])
            x, y = transformer.transform(lon, lat)
            plot_data.append({
                'plot_uri': result['plot']['value'],
                'plot_id': result['plot_id']['value'],
                'x': x,
                'y': y
            })
        return plot_data

    def fetch_sensor_data():
        query = """
        PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT ?sensor ?sensor_id ?lat ?lon
        WHERE {
            GRAPH <http://wifire.ucsd.edu/sensor_readings_location> {
                ?sensor rdf:type wifire:FireIgnitionSensor ;
                        wifire:hasLocationDataSensor ?loc .
                ?loc wifire:longitudeSensor ?lon ;
                     wifire:latitudeSensor ?lat .
                OPTIONAL {
                    ?sensor wifire:hasSensorMetadata ?meta .
                    ?meta wifire:db_id ?sensor_id .
                }
            }
        }
        """
        headers = {'Accept': 'application/sparql-results+json'}
        for attempt in range(MAX_RETRIES):
            try:
                response = session.get(
                    SPARQL_ENDPOINT, 
                    params={'query': query}, 
                    headers=headers, 
                    verify=False,
                    timeout=REQUEST_TIMEOUT
                )
                if response.status_code == 200:
                    break
                print(f"Attempt {attempt + 1} failed with status {response.status_code}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)
            except requests.exceptions.Timeout:
                print(f"Timeout on attempt {attempt + 1}")
                if attempt == MAX_RETRIES - 1:
                    print("Failed to fetch sensor data after all retries")
                    return []
                time.sleep(2)
            except requests.exceptions.RequestException as e:
                print(f"Error fetching sensor data: {e}")
                return []
        
        results = response.json()['results']['bindings']
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32610", always_xy=True)
        sensor_data = []
        for result in results:
            lon = float(result['lon']['value'])
            lat = float(result['lat']['value'])
            x, y = transformer.transform(lon, lat)
            sensor_uri = result['sensor']['value']
            sensor_id = result.get('sensor_id', {}).get('value')
            if not sensor_id:
                sensor_id = sensor_uri.split('sensor_')[-1]
            sensor_data.append({
                'sensor_uri': sensor_uri,
                'sensor_id': sensor_id,
                'x': x,
                'y': y
            })
        return sensor_data

    def create_management_areas_grouped(plot_data, sensor_data):
        if not plot_data or not sensor_data:
            print("No data points found")
            return []
        print(f"\nProcessing {len(plot_data)} plots and {len(sensor_data)} sensors")
        # Compute bounding box only for plots
        min_x = min(p['x'] for p in plot_data)
        max_x = max(p['x'] for p in plot_data)
        min_y = min(p['y'] for p in plot_data)
        max_y = max(p['y'] for p in plot_data)
        print(f"Plot bounding box: X [{min_x}, {max_x}], Y [{min_y}, {max_y}]")
        
        # Group plots by base_name
        def parse_base_name(plot_id):
            return '_'.join(plot_id.split('_')[:-2])
        plots_by_base = defaultdict(list)
        for p in plot_data:
            base_name = parse_base_name(p['plot_id'])
            plots_by_base[base_name].append(p)
        
        management_areas = []
        area_id = 1
        N = 10  # Number of closest sensors to find
        radius_meters = 2000  # Maximum distance in meters
        
        for base_name, plots in plots_by_base.items():
            # For each plot in the group, find its N closest sensors
            group_sensors = set()  # Use set to avoid duplicates
            for p in plots:
                # Compute distances to all sensors
                distances = []
                for s in sensor_data:
                    dist = np.sqrt((p['x'] - s['x'])**2 + (p['y'] - s['y'])**2)
                    if dist <= radius_meters:
                        distances.append((dist, s['sensor_id'], s['sensor_uri']))
                
                # Get top N closest sensors
                closest_sensors = sorted(distances)[:N]
                for _, sensor_id, sensor_uri in closest_sensors:
                    group_sensors.add((sensor_id, sensor_uri))
            
            if group_sensors:
                # Create a bounding box around all plots in the group
                group_x = [p['x'] for p in plots]
                group_y = [p['y'] for p in plots]
                min_gx, max_gx = min(group_x), max(group_x)
                min_gy, max_gy = min(group_y), max(group_y)
                cell_polygon = Polygon([
                    (min_gx, min_gy),
                    (max_gx, min_gy),
                    (max_gx, max_gy),
                    (min_gx, max_gy),
                    (min_gx, min_gy)
                ])
                management_areas.append({
                    'area_id': f'area_{area_id}',
                    'geometry': to_wkt(cell_polygon),
                    'plots': [(p['plot_id'], p['plot_uri']) for p in plots],
                    'sensors': list(group_sensors)
                })
                print(f"Created area_{area_id} for base_name {base_name} with {len(plots)} plots and {len(group_sensors)} sensors.")
                print("Sensor IDs in this area:", [sid for sid, _ in group_sensors])
                print("Sensor URIs in this area:", [suri for _, suri in group_sensors])
                area_id += 1
        print(f"Created {len(management_areas)} management areas.")
        return management_areas

    def save_to_graphdb(management_areas):
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': '*/*'
        }
        for area in management_areas:
            plot_statements = "\n".join(
                f'wifire:{area["area_id"]} wifire:hasPlot <{plot_uri}> .' for _, plot_uri in area['plots']
            )
            sensor_statements = "\n".join(
                f'wifire:{area["area_id"]} wifire:hasFireIgnitionSensor <{sensor_uri}> .' for _, sensor_uri in area['sensors']
            )
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            INSERT DATA {{
                GRAPH <http://wifire.ucsd.edu/fire_management_areas_grouped> {{
                    wifire:{area['area_id']} rdf:type wifire:FireManagementArea ;
                        rdfs:label "Fire Management Area" ;
                        rdfs:comment "Represents the geographical area where fire management activities are carried out" ;
                        wifire:geometry "{area['geometry']}"^^xsd:string ;
                        wifire:plotCount {len(area['plots'])} ;
                        wifire:sensorCount {len(area['sensors'])} .
                    {plot_statements}
                    {sensor_statements}
                }}
            }}
            """
            for attempt in range(MAX_RETRIES):
                try:
                    response = session.post(
                        UPDATE_ENDPOINT,
                        data={'update': update_query},
                        headers=headers,
                        verify=False,
                        timeout=REQUEST_TIMEOUT
                    )
                    if response.status_code in [200, 204]:
                        print(f"Saved area {area['area_id']} with {len(area['plots'])} plots and {len(area['sensors'])} sensors")
                        break
                    print(f"Attempt {attempt + 1} failed with status {response.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(2)
                except requests.exceptions.Timeout:
                    print(f"Timeout on attempt {attempt + 1}")
                    if attempt == MAX_RETRIES - 1:
                        print(f"Failed to save area {area['area_id']} after all retries")
                    time.sleep(2)
                except requests.exceptions.RequestException as e:
                    print(f"Error saving area {area['area_id']}: {e}")
                    break

    try:
        # Fetch data
        plot_data = fetch_plot_metrics_data()
        sensor_data = fetch_sensor_data()
        
        if not plot_data or not sensor_data:
            print("No data found in GraphDB")
            return
        
        print(f"Found {len(plot_data)} plots and {len(sensor_data)} sensors")
        
        # Create management areas
        management_areas = create_management_areas_grouped(plot_data, sensor_data)
        if management_areas:
            save_to_graphdb(management_areas)
        else:
            print("No valid management areas created")

    except Exception as e:
        print(f"Error processing and creating management areas: {str(e)}")
        raise

with DAG(
    'graphdb_management_areas_grouping_import',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='Create and import grouped fire management areas into GraphDB'
) as dag:
    install_deps = BashOperator(
        task_id='install_dependencies',
        bash_command='pip install --no-cache-dir shapely pyproj numpy requests',
    )
    create_areas = PythonOperator(
        task_id='process_and_create_grouped_areas',
        python_callable=process_and_create_grouped_areas
    )
    install_deps >> create_areas 