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


