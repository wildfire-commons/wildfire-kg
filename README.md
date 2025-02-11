# wildfire-kg

wildfire-kg is a collection of data pipelines, APIs and knowledge graphs that serve a conversational AI data product for the Immersive Forest project.

# Project Description
The initial scope and write up for this project can be found at: https://docs.google.com/document/d/1U_JBXRhjHzgEpl6_ECNciltwSGd2Baq9bNVNV1CQiUQ/edit?usp=sharing

## Overview
Contains the code and infrastructure templates for the Conversational AI portion of the conversational AI project at:https://burnpro3d.sdsc.edu/pano/?plot=CATNF_6022&ts=20240731&m=Basalarea

# Infrastructure

## Prerequisites

- A valid `config` file in ~/.kube/config for `wifire-kg` namespace
- `kubectl` CLI installed
- `docker` installed

## Airflow

### Local Development
We use docker compose to run the airflow webserver, scheduler, redis and postgres locally.

Start airflow locally at http://localhost:8080. It will load the DAGs from the `dags` folder in the repo.

```bash
docker-compose up -d
```

Tear down airflow locally

```bash
docker-compose down
```

### Deploying to Nautilus (Kubernetes)

Use utility script to deploy airflow to nautilus which runs the underlying commands. Note: You will need a valid `config` file in ~/.kube/config for `wifire-kg` namespace in order to deploy.

```bash
./deploy.sh airflow
```

<<<<<<< HEAD
=======
## Description
Contains a collection of data pipelines, APIs, and infrastructure templates to support the Conversational AI portion of the immersive forest
project at https://burnpro3d.sdsc.edu/pano/?plot=CATNF_6022&ts=20240731&m=Basalarea.
>>>>>>> cbaf9a8 (Update readme)

## Project Overview
This project implements a knowledge graph-based system for forest and wildfire data analysis. It integrates multiple data sources into a unified graph database, enabling complex queries and spatial reasoning for fuel management and forest health monitoring.   

## Key Components
- **Knowledge Graph**: Neo4j-based graph database for storing and querying forest and wildfire data
- **ETL Pipeline**: Airflow-orchestrated data processing workflows
- **GraphDB**: Ontotext GraphDB instance for semantic data storage
- **API Layer**: FastAPI-based REST API for data access
- **Dashboard**: Interactive visualization interface

## Infrastructure
The project is deployed on Kubernetes using Helm charts with the following components:
- Apache Airflow for workflow orchestration
- GraphDB for knowledge graph storage
- Kubernetes namespaces: `wifire-kg` (dev) and future: `wifire-kg-prod` (production)

## Setup and Installation

### Scripts Setup
The `scripts/` directory contains utility scripts for deployment and management:

Make scripts executable and source the functions file:
```bash
chmod +x scripts/*.sh
source scripts/functions.sh
```
   
### Deployment
Use the deployment script to deploy components:
```bash
deploy <environment> <component>
```
- Environments: dev, prod
- Components: airflow, graphdb, neo4j, all

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