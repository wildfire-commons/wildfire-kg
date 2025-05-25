from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from datetime import datetime
import os
import time
from dotenv import load_dotenv
import requests

# Load .env file
load_dotenv()

def process_and_load_data():
    # Move imports inside
    import pandas as pd
    import urllib3
    import boto3
    from botocore.config import Config
    import io
    from rdflib import Graph, Namespace, Literal, URIRef
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Get credentials from Airflow Variables
    aws_access_key_id = Variable.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = Variable.get("AWS_SECRET_ACCESS_KEY")
    aws_s3_endpoint_url = Variable.get("AWS_S3_ENDPOINT_URL")
    aws_s3_bucket_name = Variable.get("AWS_S3_BUCKET_NAME")

    # Print environment variables to debug (optional)
    print("Environment variables:")
    print(f"AWS_ACCESS_KEY_ID: {'*' * len(aws_access_key_id) if aws_access_key_id else 'Not set'}")
    print(f"AWS_SECRET_ACCESS_KEY: {'*' * 5 if aws_secret_access_key else 'Not set'}")
    print(f"AWS_S3_ENDPOINT_URL: {aws_s3_endpoint_url}")
    print(f"AWS_S3_BUCKET_NAME: {aws_s3_bucket_name}")

    # Set up S3 client with retry configuration
    s3_config = Config(
        retries=dict(
            max_attempts=5,
            mode='adaptive'
        )
    )
    
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=aws_s3_endpoint_url,
        verify=False,
        config=s3_config
    )

    # local GraphDB connection details
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

    # connection test with timeout
    try:
        test_response = session.get(
            SPARQL_ENDPOINT,
            params={'query': 'ASK { ?s ?p ?o }'},
            headers={'Accept': 'application/sparql-results+json'},
            verify=False,
            timeout=30
        )
        print(f"GraphDB connection test status: {test_response.status_code}")
        if test_response.status_code != 200:
            raise Exception(f"GraphDB connection failed with status {test_response.status_code}")
    except Exception as e:
        print(f"Error connecting to GraphDB: {str(e)}")
        raise

    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")

    print("Starting data import...")
    try:
        # Get file from S3 with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                s3_response = s3_client.get_object(
                    Bucket=aws_s3_bucket_name,
                    Key='cleaned_intelimon_metrics.csv'
                )
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"Retry {attempt + 1}/{max_retries} for S3 download: {str(e)}")
                time.sleep(2 ** attempt)  # Exponential backoff
        
        # Read CSV directly from S3 response
        df = pd.read_csv(io.BytesIO(s3_response['Body'].read()))
        print(f"Loaded {len(df)} plot metrics from S3")
        
        # Parse latlon string into separate latitude and longitude columns
        def parse_latlon(latlon_str):
            try:
                # Remove brackets and split by comma
                coords = latlon_str.strip('[]').split(',')
                # Convert to float and return as tuple (latitude, longitude)
                return float(coords[0].strip()), float(coords[1].strip())
            except (ValueError, IndexError, AttributeError):
                return None, None

        # Apply the parsing function to create new columns
        df[['Latitude', 'Longitude']] = df['latlon'].apply(parse_latlon).apply(pd.Series)
        
        def parse_plot_info(plot_id):
            # Parse plot ID into components: base_name, date, sequence
            parts = plot_id.rsplit('_', 2)
            base_name = parts[0]
            date = parts[1]
            sequence = parts[2]
            
            # Parse date into year, month, day
            year = int(date[:4])
            month = int(date[4:6])
            day = int(date[6:8])
            
            return {
                'base_name': base_name,
                'date': date,
                'sequence': sequence,
                'datetime': datetime(year, month, day)
            }

        def group_plots_by_base(plot_ids):
            # Group plots by their base name (ignoring date and sequence)
            grouped = {}
            for plot_id in plot_ids:
                info = parse_plot_info(plot_id)
                base_name = info['base_name']
                if base_name not in grouped:
                    grouped[base_name] = []
                grouped[base_name].append({
                    'plot_id': plot_id,
                    'datetime': info['datetime'],
                    'date': info['date']
                })
            return grouped

        def establish_temporal_relations(grouped_plots):
            temporal_relations = {}
            
            for base_name, plots in grouped_plots.items():
                # Sort plots by date
                sorted_plots = sorted(plots, key=lambda x: x['datetime'])
                
                for i, current_plot in enumerate(sorted_plots):
                    current_id = current_plot['plot_id']
                    current_date = current_plot['date']
                    temporal_relations[current_id] = {'next': [], 'last': []}

                    # Check if there are other plots with the same date
                    same_date_plots = [p['plot_id'] for p in sorted_plots if p['date'] == current_date and p['plot_id'] != current_id]
                    
                    if same_date_plots:
                        # For plots on same date, establish bidirectional relationships
                        temporal_relations[current_id]['next'].extend(same_date_plots)
                        temporal_relations[current_id]['last'].extend(same_date_plots)
                    else:
                        # For different dates, establish temporal relationships
                        if i > 0:  # Has previous plot
                            prev_plot = sorted_plots[i-1]
                            if prev_plot['date'] != current_date:
                                temporal_relations[current_id]['last'].append(prev_plot['plot_id'])
                        
                        if i < len(sorted_plots) - 1:  # Has next plot
                            next_plot = sorted_plots[i+1]
                            if next_plot['date'] != current_date:
                                temporal_relations[current_id]['next'].append(next_plot['plot_id'])

            return temporal_relations

        df['base_name'] = df['PLOT_NAME'].apply(lambda x: '_'.join(x.split('_')[:-1]))
        df['date_str'] = df['PLOT_NAME'].apply(lambda x: x.split('_')[-2])
        
        # Filter out rows with invalid dates
        df = df[df['date_str'].notna()]
        
        # Convert valid dates to datetime
        df['date'] = pd.to_datetime(df['date_str'], format='%Y%m%d')
        
        print(f"Processing {len(df)} plots with valid dates")
        
        # Sort by base_name and date
        df = df.sort_values(['base_name', 'date'])
        
        # After loading plot data, establish temporal relationships
        grouped_plots = group_plots_by_base(df['PLOT_NAME'].unique())
        temporal_relations = establish_temporal_relations(grouped_plots)

        successful_uploads = 0
        failed_uploads = 0
        
        total_plots = len(df)
        print(f"\nStarting upload of {total_plots} plots...")
        
        def validate_date_format(plot_name):
            """Validate date format in plot name (e.g., FLSMR_0056_20210713_1)"""
            try:
                # Extract date portion (expecting YYYYMMDD format)
                parts = plot_name.split('_')
                if len(parts) < 3:
                    return False
                date_str = parts[-2]  # Get the second to last part
                if len(date_str) != 8:  # Check if it's 8 digits
                    return False
                # Try parsing the date
                datetime.strptime(date_str, '%Y%m%d')
                return True
            except (ValueError, IndexError):
                return False

        valid_plots = []
        invalid_date_count = 0
        
        for _, plot in df.iterrows():
            plot_id = plot['PLOT_NAME']
            if validate_date_format(plot_id):
                valid_plots.append(plot)
            else:
                invalid_date_count += 1
                print(f"Warning: Invalid date format in plot name: {plot_id}")
        
        print(f"Found {len(valid_plots)} valid plots out of {len(df)} total plots")
        print(f"Invalid date format count: {invalid_date_count}")
        
        # Batch processing configuration
        BATCH_SIZE = 50  # Process 50 plots at a time
        total_batches = (len(valid_plots) + BATCH_SIZE - 1) // BATCH_SIZE
        
        geocode_cache = {}
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min((batch_idx + 1) * BATCH_SIZE, len(valid_plots))
            batch_plots = valid_plots[start_idx:end_idx]
            
            print(f"\nProcessing batch {batch_idx + 1}/{total_batches} ({start_idx + 1}-{end_idx} of {len(valid_plots)})")
            
            batch_queries = []
            for plot in batch_plots:
                plot_id = plot['PLOT_NAME']
                try:
                    if plot_id in temporal_relations:
                        temporal_info = []
                        for next_plot in temporal_relations[plot_id]['next']:
                            temporal_info.append(f"nextMetrics: {next_plot}")
                        for last_plot in temporal_relations[plot_id]['last']:
                            temporal_info.append(f"lastMetrics: {last_plot}")
                        if temporal_info:
                            print(f"Temporal relations: {', '.join(temporal_info)}")

                    lat = plot['Latitude']
                    lon = plot['Longitude']
                    city, state, country = reverse_geocode(lat, lon, geocode_cache)

                    update_query = f"""
                    PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                    
                    INSERT DATA {{ 
                        GRAPH <http://wifire.ucsd.edu/plot_metrics_temporal_geograph> {{
                            # Main PlotMetrics instance
                            wifire:plot_{plot_id} rdf:type wifire:PlotMetrics ;
                                rdfs:label "Plot Metrics" ;
                                rdfs:comment "Represents data about a specific plot of land related to fire risk and behavior" ;
                                wifire:plotName "{plot_id}"^^xsd:string ;
                                wifire:plotDate "{plot['date_str']}"^^xsd:date .
                            
                            # LocationDataPlot
                            wifire:location_{plot_id} rdf:type wifire:LocationDataPlot ;
                                rdfs:label "Location Data Plot" ;
                                rdfs:comment "Represents location data related to a plot's geographic coordinates" ;
                                wifire:plotLongitude "{lon}"^^xsd:float ;
                                wifire:plotLatitude "{lat}"^^xsd:float ;
                                wifire:plotCity "{city}"^^xsd:string ;
                                wifire:plotState "{state}"^^xsd:string ;
                                wifire:plotCountry "{country}"^^xsd:string .
                            
                            # Link PlotMetrics to LocationDataPlot
                            wifire:plot_{plot_id} wifire:hasLocationDataPlot wifire:location_{plot_id} .
                            
                            # Temporal relationships
                            {' '.join(f'wifire:plot_{plot_id} wifire:lastMetrics wifire:plot_{last_plot} .' for last_plot in temporal_relations[plot_id]["last"]) if plot_id in temporal_relations else ''}
                            {' '.join(f'wifire:plot_{plot_id} wifire:nextMetrics wifire:plot_{next_plot} .' for next_plot in temporal_relations[plot_id]["next"]) if plot_id in temporal_relations else ''}
                            
                            # VegetationMetrics
                            wifire:veg_{plot_id} rdf:type wifire:VegetationMetrics ;
                                rdfs:label "Vegetation Metrics" ;
                                rdfs:comment "Represents vegetation data collected from a plot" ;
                                wifire:basalArea "{plot['Basalarea']}"^^xsd:float ;
                                wifire:LAI "{plot['LAI']}"^^xsd:float ;
                                wifire:TBA "{plot['TBA']}"^^xsd:float ;
                                wifire:OLAI "{plot['OLAI']}"^^xsd:float ;
                                wifire:ULAI "{plot['ULAI']}"^^xsd:float ;
                                wifire:GCvol "{plot['GCvol']}"^^xsd:float ;
                                wifire:MSvol "{plot['MSvol']}"^^xsd:float ;
                                wifire:OSvol "{plot['OSvol']}"^^xsd:float ;
                                wifire:USvol "{plot['USvol']}"^^xsd:float .
                            
                            # Link PlotMetrics to VegetationMetrics
                            wifire:plot_{plot_id} wifire:hasVegetationMetrics wifire:veg_{plot_id} .
                            
                            # FireBehaviorMetrics
                            wifire:fire_{plot_id} rdf:type wifire:FireBehaviorMetrics ;
                                rdfs:label "Fire Behavior Metrics" ;
                                rdfs:comment "Captures the behavior of fire including intensity, spread, and firefront data" ;
                                wifire:LF_FBFM13 "{plot['LF_FBFM13']}"^^xsd:string ;
                                wifire:LF_FBFM40 "{plot['LF_FBFM40']}"^^xsd:string ;
                                wifire:LF_EVEL "{plot['LF_EVEL']}"^^xsd:float ;
                                wifire:LF_SLPD "{plot['LF_SLPD']}"^^xsd:float ;
                                wifire:LF_ASP "{plot['LF_ASP']}"^^xsd:float ;
                                wifire:LF_FDist "{plot['LF_FDist']}"^^xsd:string ;
                                wifire:LF_EVC "{plot['LF_EVC']}"^^xsd:string ;
                                wifire:LF_EVT "{plot['LF_EVT']}"^^xsd:string .
                            
                            # Link PlotMetrics to FireBehaviorMetrics
                            wifire:plot_{plot_id} wifire:hasFireBehaviorMetrics wifire:fire_{plot_id} .
                            
                            # TreeShrubMetrics
                            wifire:tree_{plot_id} rdf:type wifire:TreeShrubMetrics ;
                                rdfs:label "Tree Shrub Metrics" ;
                                rdfs:comment "Captures metrics related to trees and shrubs in a plot" ;
                                wifire:MDBH "{plot['MDBH']}"^^xsd:float ;
                                wifire:MLAI "{plot['MLAI']}"^^xsd:float ;
                                wifire:SDHT "{plot['SDHT']}"^^xsd:float ;
                                wifire:SDSHT "{plot['SDSHT']}"^^xsd:float ;
                                wifire:SDSD "{plot['SDSD']}"^^xsd:float ;
                                wifire:MaxSD "{plot['MaxSD']}"^^xsd:float ;
                                wifire:MaxSH "{plot['MaxSH']}"^^xsd:float ;
                                wifire:MaxTH "{plot['MaxTH']}"^^xsd:float ;
                                wifire:MinSD "{plot['MinSD']}"^^xsd:float ;
                                wifire:TreesN "{plot['TreesN']}"^^xsd:integer ;
                                wifire:ShrubsN "{plot['ShrubsN']}"^^xsd:integer ;
                                wifire:MeanSA "{plot['MeanSA']}"^^xsd:float ;
                                wifire:shrubArea "{plot['shrubArea']}"^^xsd:float ;
                                wifire:scaledShrubArea "{plot['scaledShrubArea']}"^^xsd:float ;
                                wifire:CBH "{plot['CBH']}"^^xsd:float ;
                                wifire:MeanSH "{plot['MeanSH']}"^^xsd:float ;
                                wifire:MeanTH "{plot['MeanTH']}"^^xsd:float ;
                                wifire:LF_CBD "{plot['LF_CBD']}"^^xsd:float ;
                                wifire:MeanSD "{plot['MeanSD']}"^^xsd:float .
                            
                            # Link PlotMetrics to TreeShrubMetrics
                            wifire:plot_{plot_id} wifire:hasTreeShrubMetrics wifire:tree_{plot_id} .
                        }}
                    }}
                    """
                    batch_queries.append(update_query)
                    
                except Exception as plot_error:
                    print(f"✗ Error processing plot {plot_id}: {str(plot_error)}")
                    failed_uploads += 1
                    continue
            
            # Execute batch update with retry
            if batch_queries:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Join queries with semicolons to properly terminate each query
                        combined_query = ';\n'.join(batch_queries) + ';'
                        response = session.post(
                            UPDATE_ENDPOINT,
                            data={'update': combined_query},
                            headers={'Content-Type': 'application/x-www-form-urlencoded'},
                            verify=False,
                            timeout=60
                        )
                        
                        if response.status_code in [200, 204]:
                            successful_uploads += len(batch_queries)
                            print(f"✓ Successfully uploaded batch {batch_idx + 1}")
                            break
                        else:
                            if attempt == max_retries - 1:
                                print(f"✗ Failed to upload batch {batch_idx + 1}. Status: {response.status_code}")
                                print(f"Response: {response.text}")
                                failed_uploads += len(batch_queries)
                            else:
                                print(f"Retry {attempt + 1}/{max_retries} for batch {batch_idx + 1}")
                                time.sleep(2 ** attempt)  # Exponential backoff
                    except Exception as e:
                        if attempt == max_retries - 1:
                            print(f"✗ Error uploading batch {batch_idx + 1}: {str(e)}")
                            failed_uploads += len(batch_queries)
                        else:
                            print(f"Retry {attempt + 1}/{max_retries} for batch {batch_idx + 1}: {str(e)}")
                            time.sleep(2 ** attempt)  # Exponential backoff
            
            # Add a small delay between batches to prevent overwhelming the server
            if batch_idx < total_batches - 1:
                time.sleep(1)
        
        print(f"\nUpload summary:")
        print(f"- Successfully uploaded: {successful_uploads}")
        print(f"- Failed uploads: {failed_uploads}")
        print(f"- Total plots processed: {successful_uploads + failed_uploads}")
        
        # Verify the count in GraphDB with retry
        verify_query = """
        PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT (COUNT(DISTINCT ?plot) as ?plotCount) 
        FROM <http://wifire.ucsd.edu/plot_metrics_temporal>
        WHERE {
            ?plot rdf:type wifire:PlotMetrics .
        }
        """
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                verify_response = session.get(
                    SPARQL_ENDPOINT,
                    params={'query': verify_query},
                    headers={'Accept': 'application/sparql-results+json'},
                    verify=False,
                    timeout=30
                )
                
                if verify_response.status_code == 200:
                    plot_count = verify_response.json()['results']['bindings'][0]['plotCount']['value']
                    print(f"Final count in GraphDB: {plot_count} plots")
                    break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Error verifying final count: {str(e)}")
                else:
                    print(f"Retry {attempt + 1}/{max_retries} for verification: {str(e)}")
                    time.sleep(2 ** attempt)  # Exponential backoff
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        raise

def upload_with_retries(plot_id, data, max_retries=5):
    import requests
    import urllib3
    import boto3
    import io
    from rdflib import Graph, Namespace, Literal, URIRef
    import time

    for attempt in range(max_retries):
        try:
            # Existing upload code
            return True
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            if attempt == max_retries - 1:
                print(f"Final retry failed for {plot_id}: {str(e)}")
                return False
            time.sleep(2 ** attempt)  # Exponential backoff

def reverse_geocode(lat, lon, cache=None):
    """Get city, state, country from latitude and longitude using Nominatim."""
    if cache is not None:
        key = (round(lat, 5), round(lon, 5))
        if key in cache:
            return cache[key]
    try:
        url = f"https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "zoom": 10,
            "addressdetails": 1
        }
        headers = {"User-Agent": "wildfire-kg/1.0 (your@email.com)"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("address", {})
            city = address.get("city") or address.get("town") or address.get("village") or address.get("hamlet") or address.get("municipality") or ""
            state = address.get("state", "")
            country = address.get("country", "")
            result = (city, state, country)
            if cache is not None:
                cache[key] = result
            return result
        else:
            print(f"Reverse geocoding failed for {lat},{lon}: {resp.status_code}")
            return ("", "", "")
    except Exception as e:
        print(f"Reverse geocoding error for {lat},{lon}: {str(e)}")
        return ("", "", "")

with DAG(
    'graphdb_plot_metrics_import',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='Import plot metrics data into GraphDB'
) as dag:
    
    install_deps = BashOperator(
        task_id='install_dependencies',
        bash_command='pip install --no-cache-dir rdflib requests pandas boto3',
    )
    
    load_data = PythonOperator(
        task_id='process_and_load_data',
        python_callable=process_and_load_data
    )
    
    install_deps >> load_data 