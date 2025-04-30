from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from datetime import datetime
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

def process_and_load_data():
    # Move imports inside
    import pandas as pd
    import requests
    import urllib3
    import boto3
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

    # Set up S3 client
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=aws_s3_endpoint_url,
        verify=False
    )

    # local GraphDB connection details
    GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
    REPOSITORY = "wildfire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

    # connection test
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

    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")

    print("Starting data import...")
    try:
        # Get file from S3
        s3_response = s3_client.get_object(
            Bucket=aws_s3_bucket_name,
            Key='cleaned_intelimon_metrics.csv'
        )
        
        # Read CSV directly from S3 response
        df = pd.read_csv(io.BytesIO(s3_response['Body'].read()))
        print(f"Loaded {len(df)} plot metrics from S3")
        
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
        
        for plot in valid_plots:
            plot_id = plot['PLOT_NAME']
            try:
                print(f"\nProcessing plot {plot_id} ({successful_uploads + failed_uploads + 1}/{total_plots})")
                
                if plot_id in temporal_relations:
                    temporal_info = []
                    for next_plot in temporal_relations[plot_id]['next']:
                        temporal_info.append(f"nextMetrics: {next_plot}")
                    for last_plot in temporal_relations[plot_id]['last']:
                        temporal_info.append(f"lastMetrics: {last_plot}")
                    if temporal_info:
                        print(f"Temporal relations: {', '.join(temporal_info)}")

                update_query = f"""
                PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                
                INSERT DATA {{ 
                    GRAPH <http://wifire.ucsd.edu/plot_metrics_temporal> {{
                        # Main PlotMetrics instance
                        wifire:plot_{plot_id} rdf:type wifire:PlotMetrics .
                        
                        # Temporal relationships
                        {' '.join(f'wifire:plot_{plot_id} wifire:lastMetrics wifire:plot_{last_plot} .' for last_plot in temporal_relations[plot_id]["last"]) if plot_id in temporal_relations else ''}
                        {' '.join(f'wifire:plot_{plot_id} wifire:nextMetrics wifire:plot_{next_plot} .' for next_plot in temporal_relations[plot_id]["next"]) if plot_id in temporal_relations else ''}
                        
                        # VegetationMetrics
                        wifire:veg_{plot_id} rdf:type wifire:VegetationMetrics ;
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
                            wifire:plotName "{plot_id}"^^xsd:string ;
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
                            wifire:scaledShrubArea "{plot['scaledShrubArea']}"^^xsd:float .
                        
                        # Link PlotMetrics to TreeShrubMetrics
                        wifire:plot_{plot_id} wifire:hasTreeShrubMetrics wifire:tree_{plot_id} .
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
                
                if response.status_code in [200, 204]:
                    successful_uploads += 1
                    print(f"✓ Successfully uploaded plot {plot_id}")
                else:
                    print(f"✗ Failed to add plot {plot_id}. Status: {response.status_code}")
                    print(f"Response: {response.text}")
                    failed_uploads += 1
                    
            except Exception as plot_error:
                print(f"✗ Error processing plot {plot_id}: {str(plot_error)}")
                failed_uploads += 1
                continue
            
        print(f"\nUpload summary:")
        print(f"- Successfully uploaded: {successful_uploads}")
        print(f"- Failed uploads: {failed_uploads}")
        print(f"- Total plots processed: {successful_uploads + failed_uploads}")
        
        # Verify the count in GraphDB
        verify_query = """
        PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT (COUNT(DISTINCT ?plot) as ?plotCount) 
        FROM <http://wifire.ucsd.edu/plot_metrics_temporal>
        WHERE {
            ?plot rdf:type wifire:PlotMetrics .
        }
        """
        
        verify_response = requests.get(
            SPARQL_ENDPOINT,
            params={'query': verify_query},
            headers={'Accept': 'application/sparql-results+json'},
            verify=False
        )
        
        if verify_response.status_code == 200:
            plot_count = verify_response.json()['results']['bindings'][0]['plotCount']['value']
            print(f"Final count in GraphDB: {plot_count} plots")
            
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