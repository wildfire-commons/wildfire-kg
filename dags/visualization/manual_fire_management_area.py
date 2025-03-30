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
import numpy as np
from shapely.geometry import Point, Polygon
import geopandas as gpd
from shapely.wkt import loads, dumps

# Load environment variables
load_dotenv()

# Get credentials from environment variables
aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_s3_endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL")
aws_s3_bucket_name = os.getenv("AWS_S3_BUCKET_NAME")

# Print environment variables to debug (optional)
print("Environment variables:")
print(f"AWS_ACCESS_KEY_ID: {'*' * len(aws_access_key_id) if aws_access_key_id else 'Not set'}")
print(f"AWS_SECRET_ACCESS_KEY: {'*' * 5 if aws_secret_access_key else 'Not set'}")
print(f"AWS_S3_ENDPOINT_URL: {aws_s3_endpoint_url}")
print(f"AWS_S3_BUCKET_NAME: {aws_s3_bucket_name}")

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# GraphDB connection details
GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
REPOSITORY = "wildfire-kg"
SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

# Define namespaces
WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
TIME = Namespace("http://www.w3.org/2006/time#")

def fetch_plot_metrics_data():
    """Fetch plot metrics data from GraphDB"""
    query = """
    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    
    SELECT ?plot_id ?fire_id ?tree_id ?lat ?lon
    WHERE {
        GRAPH <http://wifire.ucsd.edu/plot_metrics> {
            ?plot rdf:type wifire:PlotMetrics .
            ?plot wifire:hasFireBehaviorMetrics ?fire .
            ?plot wifire:hasTreeShrubMetrics ?tree .
            
            # Extract plot_id from URI
            BIND(REPLACE(STR(?plot), "^.*plot_", "") AS ?plot_id)
            BIND(REPLACE(STR(?fire), "^.*fire_", "") AS ?fire_id)
            BIND(REPLACE(STR(?tree), "^.*tree_", "") AS ?tree_id)
            
            # Get location data if available
            OPTIONAL {
                ?plot wifire:hasLocationData ?loc .
                ?loc wifire:latitude ?lat .
                ?loc wifire:longitude ?lon .
            }
        }
    }
    """
    
    headers = {
        'Accept': 'application/sparql-results+json'
    }
    
    response = requests.get(
        SPARQL_ENDPOINT,
        params={'query': query},
        headers=headers,
        verify=False
    )
    
    if response.status_code != 200:
        print(f"Failed to fetch plot metrics. Status: {response.status_code}")
        print(f"Response: {response.text}")
        return []
    
    results = response.json()['results']['bindings']
    plot_data = []
    
    for result in results:
        plot_id = result.get('plot_id', {}).get('value')
        lat = result.get('lat', {}).get('value')
        lon = result.get('lon', {}).get('value')
        
        # If location data is missing, we'll need to fetch it from S3
        plot_data.append({
            'plot_id': plot_id,
            'latitude': float(lat) if lat else None,
            'longitude': float(lon) if lon else None
        })
    
    return plot_data

def fetch_sensor_data():
    """Fetch sensor data from GraphDB"""
    query = """
    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    
    SELECT ?sensor_id ?lat ?lon
    WHERE {
        GRAPH <http://wifire.ucsd.edu/sensor_data> {
            ?sensor rdf:type wifire:FireIgnitionSensor .
            ?sensor wifire:hasLocationData ?loc .
            ?loc wifire:latitude ?lat .
            ?loc wifire:longitude ?lon .
            
            # Extract sensor_id from URI
            ?sensor wifire:hasSensorMetadata ?meta .
            ?meta wifire:db_id ?sensor_id .
        }
    }
    """
    
    headers = {
        'Accept': 'application/sparql-results+json'
    }
    
    response = requests.get(
        SPARQL_ENDPOINT,
        params={'query': query},
        headers=headers,
        verify=False
    )
    
    if response.status_code != 200:
        print(f"Failed to fetch sensor data. Status: {response.status_code}")
        print(f"Response: {response.text}")
        return []
    
    results = response.json()['results']['bindings']
    sensor_data = []
    
    for result in results:
        sensor_id = result.get('sensor_id', {}).get('value')
        lat = result.get('lat', {}).get('value')
        lon = result.get('lon', {}).get('value')
        
        sensor_data.append({
            'sensor_id': sensor_id,
            'latitude': float(lat),
            'longitude': float(lon)
        })
    
    return sensor_data

def fetch_missing_plot_locations(plot_data, s3_client):
    """Fetch missing plot locations from S3"""
    # Count plots with missing location data
    missing_locations = sum(1 for p in plot_data if p['latitude'] is None or p['longitude'] is None)
    
    if missing_locations == 0:
        return plot_data
    
    print(f"Found {missing_locations} plots with missing location data. Fetching from S3...")
    
    try:
        # Get file from S3
        s3_response = s3_client.get_object(
            Bucket=aws_s3_bucket_name,
            Key='metrics/CASBC_plot_metrics.csv'
        )
        
        # Read CSV directly from S3 response
        df = pd.read_csv(io.BytesIO(s3_response['Body'].read()))
        
        # Check if 'latlon' column exists
        if 'latlon' in df.columns:
            # Create a dictionary of plot_id to lat/lon
            plot_locations = {}
            for _, row in df.iterrows():
                plot_id = row['PLOT_NAME']
                latlon = row['latlon']
                
                # Parse latlon string which is in format [lat, lon]
                if isinstance(latlon, str) and latlon.startswith('[') and latlon.endswith(']'):
                    try:
                        lat_lon = eval(latlon)  # Safely evaluate the string to get the list
                        if isinstance(lat_lon, list) and len(lat_lon) == 2:
                            plot_locations[plot_id] = {
                                'latitude': lat_lon[0],
                                'longitude': lat_lon[1]
                            }
                    except:
                        print(f"Could not parse latlon for plot {plot_id}: {latlon}")
            
            # Update plot_data with missing locations
            for plot in plot_data:
                if (plot['latitude'] is None or plot['longitude'] is None) and plot['plot_id'] in plot_locations:
                    plot['latitude'] = plot_locations[plot['plot_id']]['latitude']
                    plot['longitude'] = plot_locations[plot['plot_id']]['longitude']
        else:
            print("Warning: 'latlon' column not found in CSV file")
            
    except Exception as e:
        print(f"Error fetching plot locations from S3: {str(e)}")
    
    # Count remaining plots with missing location data
    still_missing = sum(1 for p in plot_data if p['latitude'] is None or p['longitude'] is None)
    print(f"After fetching, {still_missing} plots still have missing location data")
    
    return plot_data

def add_location_to_plots(plot_data):
    """Add location data to plots in GraphDB if missing"""
    for plot in plot_data:
        if plot['latitude'] is not None and plot['longitude'] is not None:
            plot_id = plot['plot_id']
            
            # Check if location data already exists
            check_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            ASK {{
                GRAPH <http://wifire.ucsd.edu/plot_metrics> {{
                    wifire:plot_{plot_id} wifire:hasLocationData ?loc .
                }}
            }}
            """
            
            headers = {
                'Accept': 'application/sparql-results+json'
            }
            
            response = requests.get(
                SPARQL_ENDPOINT,
                params={'query': check_query},
                headers=headers,
                verify=False
            )
            
            if response.status_code != 200:
                print(f"Failed to check location data for plot {plot_id}. Status: {response.status_code}")
                continue
            
            location_exists = response.json()['boolean']
            
            if not location_exists:
                # Add location data
                update_query = f"""
                PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                
                INSERT DATA {{ 
                    GRAPH <http://wifire.ucsd.edu/plot_metrics> {{
                        # LocationData
                        wifire:location_{plot_id} rdf:type wifire:LocationData ;
                            wifire:longitude "{plot['longitude']}"^^xsd:float ;
                            wifire:latitude "{plot['latitude']}"^^xsd:float .
                        
                        # Link to LocationData
                        wifire:plot_{plot_id} wifire:hasLocationData wifire:location_{plot_id} .
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
                    print(f"Failed to add location data for plot {plot_id}. Status: {response.status_code}")
                    print(f"Response: {response.text}")
                else:
                    print(f"Successfully added location data for plot {plot_id}")

def create_management_areas(plot_data, sensor_data):
    """Create fire management areas based on geographical proximity"""
    # Filter out plots with missing coordinates
    valid_plots = [p for p in plot_data if p['latitude'] is not None and p['longitude'] is not None]
    
    if not valid_plots:
        print("No valid plot data with coordinates found")
        return []
    
    if not sensor_data:
        print("No sensor data found")
        return []
    
    print(f"Creating management areas with {len(valid_plots)} valid plots and {len(sensor_data)} sensors")
    
    # Print some sample coordinates to verify distribution
    print("Sample plot coordinates:")
    for i, p in enumerate(valid_plots[:5]):
        print(f"  Plot {i+1}: Lat {p['latitude']}, Lon {p['longitude']}")
    
    print("Sample sensor coordinates:")
    for i, s in enumerate(sensor_data[:5]):
        print(f"  Sensor {i+1}: Lat {s['latitude']}, Lon {s['longitude']}")
    
    # Convert to GeoDataFrame
    plot_gdf = gpd.GeoDataFrame(
        valid_plots, 
        geometry=[Point(p['longitude'], p['latitude']) for p in valid_plots]
    )
    
    sensor_gdf = gpd.GeoDataFrame(
        sensor_data, 
        geometry=[Point(s['longitude'], s['latitude']) for s in sensor_data]
    )
    
    # Define grid size (in degrees) - approximately 15 meters
    grid_size = 0.002  # 0.00014 for 15 meters converted to degrees 0.002 to create something
    
    # Get bounds with a buffer to ensure we include all points
    min_lon = min(plot_gdf.geometry.x.min(), sensor_gdf.geometry.x.min()) - grid_size
    max_lon = max(plot_gdf.geometry.x.max(), sensor_gdf.geometry.x.max()) + grid_size
    min_lat = min(plot_gdf.geometry.y.min(), sensor_gdf.geometry.y.min()) - grid_size
    max_lat = max(plot_gdf.geometry.y.max(), sensor_gdf.geometry.y.max()) + grid_size
    
    print(f"Geographical bounds: Lon [{min_lon}, {max_lon}], Lat [{min_lat}, {max_lat}]")
    
    # Create grid cells
    management_areas = []
    area_id = 1
    
    # Create a grid of cells
    for lon in np.arange(min_lon, max_lon, grid_size):
        for lat in np.arange(min_lat, max_lat, grid_size):
            # Create polygon for grid cell
            polygon = Polygon([
                (lon, lat),
                (lon + grid_size, lat),
                (lon + grid_size, lat + grid_size),
                (lon, lat + grid_size)
            ])
            
            # Find plots and sensors in this grid cell
            plots_in_cell = plot_gdf[plot_gdf.geometry.within(polygon)]
            sensors_in_cell = sensor_gdf[sensor_gdf.geometry.within(polygon)]
            
            # Only create management area if it contains at least one plot and one sensor
            if len(plots_in_cell) > 0 and len(sensors_in_cell) > 0:
                management_areas.append({
                    'area_id': f"area_{area_id}",
                    'geometry': dumps(polygon),
                    'plot_ids': plots_in_cell['plot_id'].tolist(),
                    'sensor_ids': sensors_in_cell['sensor_id'].tolist()
                })
                area_id += 1
                print(f"Created area_{area_id-1} with {len(plots_in_cell)} plots and {len(sensors_in_cell)} sensors")
    
    print(f"Created {len(management_areas)} management areas")
    return management_areas

def add_management_areas_to_graphdb(management_areas):
    """Add fire management areas to GraphDB"""
    for area in tqdm(management_areas, desc="Adding management areas", unit="area"):
        area_id = area['area_id']
        geometry = area['geometry']
        plot_ids = area['plot_ids']
        sensor_ids = area['sensor_ids']
        
        # Create SPARQL query
        update_query = f"""
        PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX geo: <http://www.opengis.net/ont/geosparql#>
        
        INSERT DATA {{ 
            GRAPH <http://wifire.ucsd.edu/fire_management_area> {{
                # Main FireManagementArea instance
                wifire:{area_id} rdf:type wifire:FireManagementArea ;
                    wifire:geometry "{geometry}"^^xsd:string .
                
                # Link to plots
                {' '.join([f'wifire:{area_id} wifire:hasPlot wifire:plot_{plot_id} .' for plot_id in plot_ids])}
                
                # Link to sensors
                {' '.join([f'wifire:{area_id} wifire:hasFireIgnitionSensor wifire:sensor_{sensor_id} .' for sensor_id in sensor_ids])}
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
            print(f"Failed to add management area {area_id}. Status: {response.status_code}")
            print(f"Response: {response.text}")
        else:
            print(f"Successfully added management area {area_id} with {len(plot_ids)} plots and {len(sensor_ids)} sensors")

def process_and_load_data():
    """Main function to process and load fire management area data"""
    # Set up S3 client
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=aws_s3_endpoint_url,
        verify=False
    )
    
    # Test GraphDB connection
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
    
    print("Starting Fire Management Area data import...")
    start_time = time.time()
    
    try:
        # Step 1: Fetch plot metrics data
        print("Fetching plot metrics data...")
        plot_data = fetch_plot_metrics_data()
        print(f"Found {len(plot_data)} plots")
        
        # Step 2: Fetch sensor data
        print("Fetching sensor data...")
        sensor_data = fetch_sensor_data()
        print(f"Found {len(sensor_data)} sensors")
        
        # Step 3: Fetch missing plot locations from S3
        print("Fetching missing plot locations...")
        plot_data = fetch_missing_plot_locations(plot_data, s3_client)
        
        # Step 4: Add location data to plots in GraphDB if missing
        print("Adding location data to plots...")
        add_location_to_plots(plot_data)
        
        # Step 5: Create management areas
        print("Creating management areas...")
        management_areas = create_management_areas(plot_data, sensor_data)
        print(f"Created {len(management_areas)} management areas")
        
        # Step 6: Add management areas to GraphDB
        print("Adding management areas to GraphDB...")
        add_management_areas_to_graphdb(management_areas)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\nImport completed:")
        print(f"Total management areas created: {len(management_areas)}")
        print(f"Total time: {duration:.2f} seconds")
        
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    process_and_load_data() 