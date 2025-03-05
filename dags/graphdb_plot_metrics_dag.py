from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime

def process_and_load_data():
    # Move imports inside
    import pandas as pd
    import requests
    import urllib3
    from rdflib import Graph, Namespace, Literal, URIRef
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # local GraphDB connection details
    GRAPHDB_URL = "http://host.docker.internal:7200"
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
        file_path = "/opt/airflow/data/raw/CASBC_plot_metrics.csv"
        df = pd.read_csv(file_path)
        print(f"Available columns: {df.columns.tolist()}")
        
        for _, plot in df.iterrows():
            plot_id = plot['PLOT_NAME']
            
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            INSERT DATA {{ 
                GRAPH <http://wifire.ucsd.edu/plot_metrics> {{
                    # Main PlotMetrics instance
                    wifire:plot_{plot_id} rdf:type wifire:PlotMetrics .
                    
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
                return
            
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