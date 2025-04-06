import urllib3
import requests
import pandas as pd
import boto3
import io
from rdflib import Graph, Namespace, Literal, URIRef
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

# GraphDB connection details
GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
REPOSITORY = "wildfire-kg"
SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

def process_and_load_data():
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

    print("Starting data import...")
    try:
        # Get file from S3
        s3_response = s3_client.get_object(
            Bucket=aws_s3_bucket_name,
            Key='metrics/CASBC_plot_metrics.csv'
        )
        
        # Read CSV directly from S3 response
        df = pd.read_csv(io.BytesIO(s3_response['Body'].read()))
        print(f"Available columns: {df.columns.tolist()}")
        
        # Process latlon column if it exists
        if 'latlon' in df.columns:
            # Split latlon into separate lat and lon
            df[['latitude', 'longitude']] = df['latlon'].str.strip('[]').str.split(',', expand=True).astype(float)
        
        for _, plot in df.iterrows():
            plot_id = plot['PLOT_NAME']
            
            # Prepare lat/lon values, handling both separate and combined formats
            lat_value = plot.get('latitude', plot.get('latlon', '').strip('[]').split(',')[0] if 'latlon' in plot else None)
            lon_value = plot.get('longitude', plot.get('latlon', '').strip('[]').split(',')[1] if 'latlon' in plot else None)
            
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            INSERT DATA {{ 
                GRAPH <http://wifire.ucsd.edu/plot_metrics> {{
                    # Main PlotMetrics instance
                    wifire:plot_{plot_id} rdf:type wifire:PlotMetrics .
                    
                    # LocationData
                    wifire:location_{plot_id} rdf:type wifire:LocationData ;
                        wifire:longitude "{lon_value}"^^xsd:float ;
                        wifire:latitude "{lat_value}"^^xsd:float .
                    
                    # Link PlotMetrics to LocationData
                    wifire:plot_{plot_id} wifire:hasLocationData wifire:location_{plot_id} .
                    
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
            
            if response.status_code not in [200, 204]:
                print(f"Failed to add plot {plot_id}. Status: {response.status_code}")
                print(f"Response: {response.text}")
                return
            
            print(f"Successfully added plot {plot_id}")
        
        print(f"Successfully loaded {len(df)} plot metrics to GraphDB")
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    process_and_load_data() 