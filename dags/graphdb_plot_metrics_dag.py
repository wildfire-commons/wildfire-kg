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
    GRAPHDB_URL = "https://graphdb-dev-wildfire-kg.nrp-nautilus.io"
    REPOSITORY = "wildfire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"

    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")

    print("Starting data import...")
    try:
        file_path = "/opt/airflow/dags/data/raw/CASBC_plot_metrics.csv"
        df = pd.read_csv(file_path)
        
        # convert latlon string to actual coordinates
        df['latitude'] = df['latlon'].str.extract(r'\[(.*?),').astype(float)
        df['longitude'] = df['latlon'].str.extract(r',\s*(.*?)\]').astype(float)
        
        # process each plot
        for _, plot in df.iterrows():
            plot_id = plot['PLOT_NAME']
            
            update_query = f"""
            PREFIX wifire: <http://wifire.ucsd.edu/ontology/>
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            INSERT {{ 
                GRAPH <http://wifire.ucsd.edu/plot_metrics> {{
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
                        wifire:scaledShrubArea "{plot['scaledShrubArea']}"^^xsd:float .
                        
                    wifire:loc_{plot_id} 
                        wifire:type geo:Feature ;
                        wifire:longitude "{plot['longitude']}"^^xsd:float ;
                        wifire:latitude "{plot['latitude']}"^^xsd:float .
                }}
            }} WHERE {{}}
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
                print(f"Failed to add plot {plot_id}. Status: {response.status_code}")
                return
            
        print(f"Successfully loaded {len(df)} plot metrics to GraphDB")
            
    except Exception as e:
        print(f"Error processing and loading data: {str(e)}")

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