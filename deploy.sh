#!/bin/bash

# Exit on any error
set -e

# Variables
NAMESPACE="wifire-kg"
TIMEOUT="300s"  # 5 minutes timeout

# Check if an argument is provided
if [ "$1" != "airflow" ]; then
    echo "Usage: ./deploy.sh airflow"
    echo "Please specify 'airflow' as an argument to deploy Airflow"
    exit 1
fi

echo "Deploying Airflow to namespace: $NAMESPACE"

# Delete existing resources if they exist
echo "Cleaning up existing resources..."
kubectl delete deployment postgres redis airflow-webserver airflow-scheduler airflow-worker --namespace $NAMESPACE --ignore-not-found
kubectl delete service postgres redis airflow-webserver --namespace $NAMESPACE --ignore-not-found
kubectl delete configmap airflow-config --namespace $NAMESPACE --ignore-not-found

# Deploy Redis and Postgres first
echo "Deploying Redis and Postgres..."
kubectl apply -f iac/airflow/airflow.redis.yaml
kubectl apply -f iac/airflow/airflow.postgres.yaml

# Give the deployments a moment to create pods
echo "Waiting for pods to be created..."
sleep 10

# Wait for Redis and Postgres to be ready using deployment conditions instead of pod labels
echo "Waiting for Redis and Postgres deployments to be ready..."
kubectl wait --for=condition=Available=True deployment/redis -n $NAMESPACE --timeout=$TIMEOUT
kubectl wait --for=condition=Available=True deployment/postgres -n $NAMESPACE --timeout=$TIMEOUT

# Deploy main Airflow configuration
echo "Deploying Airflow components..."
kubectl apply -f iac/airflow/airflow.yaml

# Wait for Airflow deployments to be ready
echo "Waiting for Airflow components..."
kubectl wait --for=condition=Available=True deployment/airflow-webserver -n $NAMESPACE --timeout=$TIMEOUT
kubectl wait --for=condition=Available=True deployment/airflow-scheduler -n $NAMESPACE --timeout=$TIMEOUT
kubectl wait --for=condition=Available=True deployment/airflow-worker -n $NAMESPACE --timeout=$TIMEOUT

echo "Airflow deployment completed successfully!"
echo "You can access the Airflow UI at: https://wifire-kg-airflow.nrp-nautilus.io"

# Print pod status
echo "Current pod status:"
kubectl get pods -n $NAMESPACE