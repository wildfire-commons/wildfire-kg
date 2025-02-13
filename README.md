# Immersive Forest

## Description
Contains the code and infrastructure templates for the Conversational AI portion of the immersive forest
project at https://burnpro3d.sdsc.edu/pano/?plot=CATNF_6022&ts=20240731&m=Basalarea

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
- Components: airflow, graphdb, all

## Project Structure
```
wildfire-kg/
├── src/                    # Source code
│   ├── api/               # API endpoints
│   ├── kg/                # Knowledge graph operations
│   ├── model/             # Machine learning models
│   └── utils/             # Utility functions
├── data/                  # Data directory
│   ├── raw/              # Raw input data
│   ├── intermediate/     # Processed data
│   └── mart/             # Final data products
├── notebooks/             # Jupyter notebooks
├── iac/                   # Infrastructure as Code
│   └── helm/             # Helm charts and values
└── scripts/              # Deployment and utility scripts
```