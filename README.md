# wildfire-kg

## Project Overview

This project implements a knowledge graph-based system for fuel management and forest health monitoring. It integrates multiple data sources into a unified knowledge graph database, enabling complex spatially and temporally aware queries. An LLM can then be used to reason over the graph to answer questions about the forest and wildfire data. 

## Key Components

- **Knowledge Graph**: Neo4j-based graph database for storing and querying forest and wildfire data
- **ETL Pipeline**: Airflow-orchestrated data processing workflows
- **GraphDB**: Ontotext GraphDB instance for semantic data storage
- **API Layer**: FastAPI-based REST API for data access
- **Dashboard**: Interactive visualization interface

## Infrastructure

The project is deployed on Kubernetes using Helm charts with the following components:
- Apache Airflow for workflow orchestration
- GraphDB/Neo4j for knowledge graph storage
- Soon: 
  - LangGraph for LLM workflow orchestration

## Prerequisites

- A valid `config` file in ~/.kube/config for `wifire-kg` namespace
- `kubectl` CLI installed
- `helm` CLI installed
- `docker` installed

## Setup and Installation

### Scripts Setup
The `scripts/` directory contains utility scripts for deployment and management:

Make scripts executable and source the functions file:
```bash
chmod +x scripts/*.sh
source scripts/functions.sh
```

## Running the Application
The application includes the frontend and backend API.

First, make environment variables available in your shell:

```bash
export AWS_ACCESS_KEY_ID="your_access_key_id"
export AWS_SECRET_ACCESS_KEY="your_secret_access_key"
export AWS_DEFAULT_REGION="us-east-1"
export AWS_S3_ENDPOINT_URL="https://s3-west.nrp-nautilus.io"
export AWS_S3_BUCKET_NAME="your_bucket_name"
```

Then, run the application locally which uses docker compose:

``` 
./run.sh app -b 
```

### Deployment to Nautilus (Kubernetes)
Use the deployment script to deploy components. Note: You will need a valid `config` file in ~/.kube/config for `wifire-kg` namespace in order to deploy.
```bash
deploy <environment> <component>
```
- Environments: dev, prod
- Components: airflow, graphdb, neo4j, all

### Airflow

#### Local Development

We use docker compose to run the airflow webserver, scheduler, redis and postgres locally.

Start airflow locally at http://localhost:8080. It will load the DAGs from the `dags` folder in the repo.

```bash
./run.sh airflow -b
```

## Project Structure
```
wildfire-kg/
├── src/                   # Source code
│   ├── api/               # API endpoints
│   ├── kg/                # Knowledge graph operations
│   ├── model/             # Machine learning models
│   └── utils/             # Utility functions
├── data/                  # Data directory
│   ├── raw/               # Raw input data
│   ├── intermediate/      # Processed data
│   └── mart/              # Final data products
├── notebooks/             # Jupyter notebooks
├── iac/                   # Infrastructure as Code
│   ├── helm/              # Helm charts and values
│   │   └── values/        # Values for overriding default Helm chart values
│   │       ├── dev/       # Dev values
│   │       └── prod/      # Prod values
│   └── manifests/         # Historical Manifests for the project
└── scripts/               # Deployment and utility scripts
```

## Storage

### Ceph S3
Storage via the Nautilus Ceph cluster that complies with the S3 API.

`aws s3api create-bucket --bucket <bucket-name> --profile <aws-profile-name> --endpoint-url https://s3-west.nrp-nautilus.io`

