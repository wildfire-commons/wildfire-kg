#!/bin/bash

# Exit on any error
set -e

# Variables
NAMESPACE="wifire-kg"
TIMEOUT="600s"  # 10 minutes timeout

# Check if an argument is provided
if [ "$1" != "airflow" ]; then
    echo "Usage: ./deploy.sh airflow"
    echo "Please specify 'airflow' as an argument to deploy Airflow"
    exit 1
fi

echo "Deploying Airflow to namespace: $NAMESPACE"

# More aggressive cleanup of existing resources
echo "Cleaning up existing resources..."
helm uninstall airflow --namespace $NAMESPACE || true
kubectl delete deployment,statefulset,service,configmap,secret,ingress -l app=airflow --namespace $NAMESPACE --ignore-not-found
kubectl delete pvc -l app=airflow --namespace $NAMESPACE --ignore-not-found
kubectl delete pod -l app=airflow --namespace $NAMESPACE --force --grace-period=0 || true

# Wait for resources to be fully cleaned up
echo "Waiting for resources to be cleaned up..."
sleep 30

# Install Airflow using Helm with basic configuration
echo "Installing Airflow using Helm..."
helm upgrade --install airflow apache-airflow/airflow \
  --namespace $NAMESPACE \
  --values iac/helm/values/airflow.values.yaml \
  --timeout $TIMEOUT \
  --wait \
  --atomic \
  --debug

# Check deployment status
echo "Checking deployment status..."
kubectl get pods -n $NAMESPACE -l release=airflow
