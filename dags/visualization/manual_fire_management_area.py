import urllib3
import requests
import json
from shapely.geometry import Point, Polygon
from shapely import to_wkt, wkt
import math
from dotenv import load_dotenv
import os
import time
import numpy as np
from pyproj import Transformer

# Load environment variables
load_dotenv()

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# GraphDB connection details
GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
REPOSITORY = "wildfire-kg"
SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"

def fetch_plot_metrics_data():
    """Fetch plot metrics data from GraphDB"""
    query = """
    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    
    SELECT ?plot ?plot_id ?lat ?lon
    WHERE {
        GRAPH <http://wifire.ucsd.edu/plot_metrics> {
            ?plot rdf:type wifire:PlotMetrics ;
                  wifire:hasLocationData ?loc .
            
            # Extract plot_id from URI
            BIND(REPLACE(STR(?plot), "^.*plot_", "") AS ?plot_id)
            
            ?loc wifire:latitude ?lat ;
                 wifire:longitude ?lon .
        }
    }
    """
    
    headers = {'Accept': 'application/sparql-results+json'}
    response = requests.get(SPARQL_ENDPOINT, params={'query': query}, headers=headers, verify=False)
    
    if response.status_code != 200:
        print(f"Failed to fetch plot metrics. Status: {response.status_code}")
        return []
    
    results = response.json()['results']['bindings']
    plot_data = []
    
    for result in results:
        plot_data.append({
            'plot_uri': result['plot']['value'],
            'plot_id': result['plot_id']['value'],
            'latitude': float(result['lat']['value']),
            'longitude': float(result['lon']['value'])
        })
    
    return plot_data

def fetch_sensor_data():
    """Fetch sensor data from GraphDB"""
    query = """
    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    
    SELECT ?sensor ?sensor_id ?lat ?lon
    WHERE {
        GRAPH <http://wifire.ucsd.edu/sensor_data> {
            ?sensor rdf:type wifire:FireIgnitionSensor ;
                    wifire:hasLocationData ?loc ;
                    wifire:hasSensorMetadata ?meta .
            
            ?meta wifire:db_id ?sensor_id .
            ?loc wifire:latitude ?lat ;
                 wifire:longitude ?lon .
        }
    }
    """
    
    headers = {'Accept': 'application/sparql-results+json'}
    response = requests.get(SPARQL_ENDPOINT, params={'query': query}, headers=headers, verify=False)
    
    if response.status_code != 200:
        print(f"Failed to fetch sensor data. Status: {response.status_code}")
        return []
    
    results = response.json()['results']['bindings']
    sensor_data = []
    
    for result in results:
        sensor_data.append({
            'sensor_uri': result['sensor']['value'],
            'sensor_id': result['sensor_id']['value'],
            'latitude': float(result['lat']['value']),
            'longitude': float(result['lon']['value'])
        })
    
    return sensor_data

def validate_management_area(area):
    """Validate that a management area has all required components"""
    required_fields = ['geometry', 'plots', 'sensors']
    missing_fields = [field for field in required_fields if not area.get(field)]
    
    if missing_fields:
        print(f"Management area {area.get('area_id')} missing required fields: {missing_fields}")
        return False
    
    # Validate WKT geometry
    try:
        polygon = wkt.loads(area['geometry'])
        if not polygon.is_valid:
            print(f"Invalid geometry for area {area.get('area_id')}")
            return False
    except Exception as e:
        print(f"Error validating geometry for area {area.get('area_id')}: {e}")
        return False
    
    return True

def create_management_areas(plot_data, sensor_data):
    """Create non-overlapping fire management areas based on 15-meter boundary using WKT"""
    if not plot_data or not sensor_data:
        print("No data points found")
        return []
    
    print(f"Processing {len(plot_data)} plots and {len(sensor_data)} sensors")
    
    # Convert to Points with their IDs
    plot_points = [(Point(p['longitude'], p['latitude']), p['plot_id'], p['plot_uri']) for p in plot_data]
    sensor_points = [(Point(s['longitude'], s['latitude']), s['sensor_id'], s['sensor_uri']) for s in sensor_data]
    
    # Get bounds
    all_points = [p[0] for p in plot_points + sensor_points]
    min_lon = min(p.x for p in all_points)
    max_lon = max(p.x for p in all_points)
    min_lat = min(p.y for p in all_points)
    max_lat = max(p.y for p in all_points)
    
    print(f"Bounds: Lon [{min_lon}, {max_lon}], Lat [{min_lat}, {max_lat}]")
    
    # Convert 15 meters to degrees
    lat_center = (min_lat + max_lat) / 2
    lon_degree_size = 15 / (111111 * math.cos(math.radians(lat_center)))
    lat_degree_size = 15 / 111111  # Latitude degrees are constant
    
    print(f"Grid size: {lon_degree_size} degrees lon, {lat_degree_size} degrees lat")
    
    # Create non-overlapping grid cells
    management_areas = []
    area_id = 1
    assigned_points = set()  # Track points that have been assigned to areas
    
    for lat in np.arange(min_lat, max_lat, lat_degree_size):
        for lon in np.arange(min_lon, max_lon, lon_degree_size):
            cell_polygon = Polygon([
                (lon, lat),
                (lon + lon_degree_size, lat),
                (lon + lon_degree_size, lat + lat_degree_size),
                (lon, lat + lat_degree_size),
                (lon, lat)
            ])
            
            # Find unassigned points within this cell
            plots_in_cell = []
            sensors_in_cell = []
            
            for point, pid, uri in plot_points:
                if uri not in assigned_points and cell_polygon.contains(point):
                    plots_in_cell.append((pid, uri))
            
            for point, sid, uri in sensor_points:
                if uri not in assigned_points and cell_polygon.contains(point):
                    sensors_in_cell.append((sid, uri))
            
            # Create area if it has any points
            if plots_in_cell or sensors_in_cell:
                area = {
                    'area_id': f'area_{area_id}',
                    'geometry': to_wkt(cell_polygon),
                    'plots': plots_in_cell,
                    'sensors': sensors_in_cell
                }
                
                # Add points to assigned set
                for _, uri in plots_in_cell:
                    assigned_points.add(uri)
                for _, uri in sensors_in_cell:
                    assigned_points.add(uri)
                
                management_areas.append(area)
                print(f"Created area_{area_id} with {len(plots_in_cell)} plots and {len(sensors_in_cell)} sensors")
                area_id += 1
    
    # Report results
    total_points = len(plot_points) + len(sensor_points)
    print(f"\nTotal points: {total_points}, Assigned points: {len(assigned_points)}")
    print(f"Created {len(management_areas)} valid management areas")
    
    return management_areas

def save_to_graphdb(management_areas):
    """Save management areas to GraphDB using WKT format and link to plots and sensors"""
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': '*/*'
    }
    
    # Save each area
    for area in management_areas:
        # Create relationship statements
        plot_statements = "\n".join(
            f'wifire:{area["area_id"]} wifire:hasPlot <{plot_uri}> .'
            for _, plot_uri in area['plots']
        )
        
        sensor_statements = "\n".join(
            f'wifire:{area["area_id"]} wifire:hasFireIgnitionSensor <{sensor_uri}> .'
            for _, sensor_uri in area['sensors']
        )
        
        update_query = f"""
        PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
        PREFIX geo: <http://www.opengis.net/ont/geosparql#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        INSERT DATA {{
            GRAPH <http://wifire.ucsd.edu/management_areas1> {{
                wifire:{area['area_id']} rdf:type wifire:FireManagementArea ;
                    geo:asWKT "{area['geometry']}"^^geo:wktLiteral ;
                    wifire:plotCount {len(area['plots'])} ;
                    wifire:sensorCount {len(area['sensors'])} .
                
                # Add relationships to plots and sensors
                {plot_statements}
                {sensor_statements}
            }}
        }}
        """
        
        response = requests.post(
            f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements",
            data={'update': update_query},
            headers=headers,
            verify=False,
            timeout=30
        )
        
        if response.status_code not in [200, 204]:
            print(f"Failed to save area {area['area_id']}. Status: {response.status_code}")
            print(f"Response: {response.text}")
            print(f"Query: {update_query}")  # Print query for debugging
        else:
            print(f"Saved area {area['area_id']} with {len(area['plots'])} plots and {len(area['sensors'])} sensors")

def main():
    """Main execution function"""
    # Fetch data from GraphDB
    plot_data = fetch_plot_metrics_data()
    sensor_data = fetch_sensor_data()
    
    if not plot_data and not sensor_data:
        print("No data found in GraphDB")
        return
    
    print(f"Found {len(plot_data)} plots and {len(sensor_data)} sensors")
    
    # Create management areas
    management_areas = create_management_areas(plot_data, sensor_data)
    
    # Save to GraphDB with relationships
    if management_areas:
        save_to_graphdb(management_areas)
    else:
        print("No valid management areas created")

if __name__ == "__main__":
    main() 