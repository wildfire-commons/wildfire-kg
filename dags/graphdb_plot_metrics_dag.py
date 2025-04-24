from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime
from airflow.models import Variable

def process_and_load_data():
    # Move imports inside
    import pandas as pd
    import requests
    import urllib3
    import boto3
    from rdflib import Graph, Namespace, Literal, URIRef
    import io
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Get S3 and GraphDB variables from Airflow
    try:
        aws_access_key = Variable.get("AWS_ACCESS_KEY_ID")
        aws_secret_key = Variable.get("AWS_SECRET_ACCESS_KEY")
        endpoint_url = Variable.get("AWS_S3_ENDPOINT_URL")
        bucket_name = Variable.get("AWS_S3_BUCKET_NAME")
        graph_name = Variable.get("GRAPHDB_GRAPH_NAME", "http://wifire.ucsd.edu/plot_metrics")
    except KeyError as e:
        print(f"Missing required Airflow variable: {str(e)}")
        raise

    # Initialize S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        endpoint_url=endpoint_url
    )

    # GraphDB connection details
    GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
    REPOSITORY = "wildfire-kg"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")

    print("Starting data import...")
    try:
        # Download file from S3
        obj = s3_client.get_object(Bucket=bucket_name, Key='cleaned_intelimon_metrics.csv')
        df = pd.read_csv(io.BytesIO(obj['Body'].read()))
        
        # Process latlon column if it exists
        if 'latlon' in df.columns:
            # Split latlon into separate lat and lon
            df[['latitude', 'longitude']] = df['latlon'].str.strip('[]').str.split(',', expand=True).astype(float)
        
        # Process each plot
        for _, plot in df.iterrows():
            plot_id = plot['PLOT_NAME']
            
            # Prepare lat/lon values, handling both separate and combined formats
            lat_value = plot.get('latitude', plot.get('latlon', '').strip('[]').split(',')[0] if 'latlon' in plot else None)
            lon_value = plot.get('longitude', plot.get('latlon', '').strip('[]').split(',')[1] if 'latlon' in plot else None)
            
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            INSERT DATA {{ 
                GRAPH <{graph_name}> {{
                    wifire:plot_{plot_id} 
                        wifire:hasID "{plot_id}" ;
                        wifire:hasLocation wifire:loc_{plot_id} ;
                        wifire:type wifire:PlotMetrics ;
                        wifire:canopyBaseHeight "{plot['CBH']}"^^xsd:float ;
                        wifire:leafAreaIndex "{plot['LAI']}"^^xsd:float ;
                        wifire:totalBasalArea "{plot['TBA']}"^^xsd:float ;
                        wifire:meanDBH "{plot['MDBH']}"^^xsd:float ;
                        wifire:meanLAI "{plot['MLAI']}"^^xsd:float ;
                        wifire:overstoryLAI "{plot['OLAI']}"^^xsd:float ;
                        wifire:understoryLAI "{plot['ULAI']}"^^xsd:float ;
                        wifire:groundCoverVolume "{plot['GCvol']}"^^xsd:float ;
                        wifire:midstoryVolume "{plot['MSvol']}"^^xsd:float ;
                        wifire:maxShrubDensity "{plot['MaxSD']}"^^xsd:float ;
                        wifire:maxShrubHeight "{plot['MaxSH']}"^^xsd:float ;
                        wifire:maxTreeHeight "{plot['MaxTH']}"^^xsd:float ;
                        wifire:minShrubDensity "{plot['MinSD']}"^^xsd:float ;
                        wifire:overstoryVolume "{plot['OSvol']}"^^xsd:float ;
                        wifire:understoryVolume "{plot['USvol']}"^^xsd:float ;
                        wifire:landFireAspect "{plot['LF_ASP']}"^^xsd:float ;
                        wifire:landFireCanopyBulkDensity "{plot['LF_CBD']}"^^xsd:float ;
                        wifire:landFireExistingVegetationCover "{plot['LF_EVC']}"^^xsd:string ;
                        wifire:landFireExistingVegetationType "{plot['LF_EVT']}"^^xsd:string ;
                        wifire:meanShrubArea "{plot['MeanSA']}"^^xsd:float ;
                        wifire:meanShrubDensity "{plot['MeanSD']}"^^xsd:float ;
                        wifire:meanShrubHeight "{plot['MeanSH']}"^^xsd:float ;
                        wifire:meanTreeHeight "{plot['MeanTH']}"^^xsd:float ;
                        wifire:numberOfTrees "{plot['TreesN']}"^^xsd:integer ;
                        wifire:landFireElevation "{plot['LF_EVEL']}"^^xsd:float ;
                        wifire:landFireSlope "{plot['LF_SLPD']}"^^xsd:float ;
                        wifire:numberOfShrubs "{plot['ShrubsN']}"^^xsd:integer ;
                        wifire:landFireDisturbance "{plot['LF_FDist']}"^^xsd:string ;
                        wifire:basalArea "{plot['Basalarea']}"^^xsd:float ;
                        wifire:landFireFuelModel13 "{plot['LF_FBFM13']}"^^xsd:string ;
                        wifire:landFireFuelModel40 "{plot['LF_FBFM40']}"^^xsd:string ;
                        wifire:shrubArea "{plot['shrubArea']}"^^xsd:float ;
                        wifire:scaledShrubArea "{plot['scaledShrubArea']}"^^xsd:float ;
                        wifire:latlon "{plot.get('latlon', '')}" .

                    wifire:loc_{plot_id} 
                        wifire:type geo:Feature ;
                        wifire:longitude "{lon_value}"^^xsd:float ;
                        wifire:latitude "{lat_value}"^^xsd:float .
                }}
            }}
            """
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': '*/*'
            }
            
            try:
                response = requests.post(
                    UPDATE_ENDPOINT,
                    data={'update': update_query},
                    headers=headers
                )
                
                if response.status_code not in [200, 204]:
                    print(f"Failed to add plot {plot_id}. Status: {response.status_code}")
                    print(f"Response content: {response.text}")
                    continue  # Skip this plot but continue with others
                
            except requests.exceptions.RequestException as e:
                print(f"Request failed for plot {plot_id}: {str(e)}")
                continue  # Skip this plot but continue with others
            
        print(f"Successfully loaded {len(df)} plot metrics to GraphDB")
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        raise

with DAG(
    'graphdb_plot_metrics_import',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='Import plot metrics data into GraphDB'
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