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

    # Get credentials from Airflow Variables
    aws_access_key_id = Variable.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = Variable.get("AWS_SECRET_ACCESS_KEY")
    aws_s3_endpoint_url = Variable.get("AWS_S3_ENDPOINT_URL")
    aws_s3_bucket_name = Variable.get("AWS_S3_BUCKET_NAME")

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
    GRID_SIZE = 200.0  # meters (can be adjusted)
    SENSOR_RADIUS = 200.0  # meters (search radius for sensors near plot)

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
        # Build spatial index for sensors (simple grid binning)
        sensor_grid = defaultdict(list)
        for s in sensor_data:
            x_idx = int((s['x'] - min_x) // GRID_SIZE)
            y_idx = int((s['y'] - min_y) // GRID_SIZE)
            sensor_grid[(x_idx, y_idx)].append(s)
        # Group plots by base_name
        def parse_base_name(plot_id):
            return '_'.join(plot_id.split('_')[:-2])
        plots_by_base = defaultdict(list)
        for p in plot_data:
            base_name = parse_base_name(p['plot_id'])
            plots_by_base[base_name].append(p)
        management_areas = []
        area_id = 1
        for base_name, plots in plots_by_base.items():
            # Collect all sensors near any plot in this group
            group_sensors = set()
            for p in plots:
                x_idx = int((p['x'] - min_x) // GRID_SIZE)
                y_idx = int((p['y'] - min_y) // GRID_SIZE)
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        cell = (x_idx + dx, y_idx + dy)
                        for s in sensor_grid.get(cell, []):
                            dist = np.sqrt((p['x'] - s['x'])**2 + (p['y'] - s['y'])**2)
                            if dist <= SENSOR_RADIUS:
                                group_sensors.add((s['sensor_id'], s['sensor_uri']))
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
                GRAPH <http://wifire.ucsd.edu/fire_management_areas_radius> {{
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
        plot_data = fetch_plot_metrics_data()
        sensor_data = fetch_sensor_data()
        if not plot_data and not sensor_data:
            print("No data found in GraphDB")
            return
        print(f"Found {len(plot_data)} plots and {len(sensor_data)} sensors")
        management_areas = create_management_areas_grouped(plot_data, sensor_data)
        if management_areas:
            save_to_graphdb(management_areas)
        else:
            print("No valid management areas created")

        # Analyze connections between plots and sensors
        print("\nAnalyzing connections between plots and sensors...")
        # 1. Filter by UTM coordinates (approximately -95 to -75 degrees longitude in UTM zone 10N)
        utm_min_x = 500000  # approximately -95 degrees in UTM zone 10N
        utm_max_x = 700000  # approximately -75 degrees in UTM zone 10N
        
        print(f"Filtering plots and sensors in UTM X range: [{utm_min_x}, {utm_max_x}]")
        df_plots_region = pd.DataFrame(plot_data)[['plot_uri', 'x', 'y']][(pd.DataFrame(plot_data)['x'] >= utm_min_x) & (pd.DataFrame(plot_data)['x'] <= utm_max_x)]
        df_sensors_region = pd.DataFrame(sensor_data)[['sensor_uri', 'x', 'y']][(pd.DataFrame(sensor_data)['x'] >= utm_min_x) & (pd.DataFrame(sensor_data)['x'] <= utm_max_x)]
        
        print(f"Found {len(df_plots_region)} plots and {len(df_sensors_region)} sensors in the specified UTM range")

        # 2. For each plot, find top N closest sensors within a radius
        N = 10
        radius_meters = 50000  # 50 km in meters (since we're using UTM coordinates)

        connections = []
        for _, plot in df_plots_region.iterrows():
            plot_coord = (plot['x'], plot['y'])
            # Compute Euclidean distances to all sensors in region (UTM coordinates are in meters)
            df_sensors_region['distance'] = df_sensors_region.apply(
                lambda row: np.sqrt((plot_coord[0] - row['x'])**2 + (plot_coord[1] - row['y'])**2), axis=1
            )
            # Filter by radius and get top N
            nearby = df_sensors_region[df_sensors_region['distance'] <= radius_meters].nsmallest(N, 'distance')
            for _, sensor in nearby.iterrows():
                connections.append({
                    'plot_uri': plot['plot_uri'],
                    'sensor_uri': sensor['sensor_uri'],
                    'distance_meters': sensor['distance']
                })

        # Convert to DataFrame for inspection
        df_connections = pd.DataFrame(connections)
        print("\nAll connections found:")
        print(df_connections)

        # Print the connections in a readable format
        if not df_connections.empty:
            print("\nTop N closest sensors for each plot in the UTM range:")
            for plot_uri in df_connections['plot_uri'].unique():
                print(f"\nPlot: {plot_uri}")
                plot_connections = df_connections[df_connections['plot_uri'] == plot_uri]
                for _, row in plot_connections.iterrows():
                    print(f"  Sensor: {row['sensor_uri']} | Distance: {row['distance_meters']:.2f} meters")
        else:
            print("No connections found in the specified UTM range and radius.")

    except Exception as e:
        print(f"Error processing and creating management areas: {str(e)}")
        raise

with DAG(
    'graphdb_management_areas_grouped_import',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='Create and import grouped fire management areas into GraphDB'
) as dag:
    install_deps = BashOperator(
        task_id='install_dependencies',
        bash_command='pip install --no-cache-dir shapely pyproj numpy requests geopy',
    )
    create_areas = PythonOperator(
        task_id='process_and_create_grouped_areas',
        python_callable=process_and_create_grouped_areas
    )
    install_deps >> create_areas 