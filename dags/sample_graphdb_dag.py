from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

def create_lidar_scan_triple(**context):
    """Creates a LiDAR scan triple in GraphDB using SPARQL."""
    # Import dependencies after they're installed
    from rdflib import Graph, Namespace, Literal, URIRef
    from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
    
    # GraphDB connection details
    GRAPHDB_URL = "http://graphdb:7200"
    REPOSITORY = "wifire-kg"
    SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    UPDATE_ENDPOINT = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"
    
    # Define namespaces
    WIFIRE = Namespace("http://wifire.ucsd.edu/ontology/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    TIME = Namespace("http://www.w3.org/2006/time#")
    
    # Initialize the SPARQL store with both query and update endpoints
    store = SPARQLUpdateStore()
    store.open((SPARQL_ENDPOINT, UPDATE_ENDPOINT))
    
    # Create a new graph
    g = Graph(store)
    
    # Bind namespaces
    g.bind('wifire', WIFIRE)
    g.bind('geo', GEO)
    g.bind('time', TIME)
    
    # Create URIs and literals for our triple
    scan_id = "LIDAR_001"
    scan_uri = URIRef(f"{WIFIRE}LidarScan_{scan_id}")
    location_uri = URIRef(f"{WIFIRE}Location_SanDiego")
    timestamp = Literal(datetime.now().isoformat())
    
    # Add triples to the graph
    g.add((scan_uri, WIFIRE.hasID, Literal(scan_id)))
    g.add((scan_uri, WIFIRE.capturedAt, location_uri))
    g.add((scan_uri, TIME.hasTime, timestamp))
    g.add((scan_uri, WIFIRE.type, WIFIRE.LidarScan))
    g.add((location_uri, WIFIRE.type, GEO.Feature))
    g.add((location_uri, WIFIRE.name, Literal("San Diego")))
    
    return f"Created LiDAR scan triple with ID: {scan_id}"

with DAG(
    'lidar_scan_dag',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    description='DAG for creating LiDAR scan triples in GraphDB'
) as dag:

    # Install required dependencies
    install_deps = BashOperator(
        task_id='install_dependencies',
        bash_command="""
            pip install rdflib==7.0.0 \
                      SPARQLWrapper==2.0.0 \
                      requests==2.31.0
        """,
    )

    create_triple = PythonOperator(
        task_id='create_lidar_triple',
        python_callable=create_lidar_scan_triple,
        provide_context=True
    )

    # Set task dependencies
    install_deps >> create_triple 