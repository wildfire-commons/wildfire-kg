#!/bin/bash

# Exit on any error
set -e

# Variables
NAMESPACE="wifire-kg"

# Check if an argument is provided
if [ "$1" != "airflow" ]; then
    echo "Usage: ./deploy.sh airflow"
    echo "Please specify 'airflow' as an argument to deploy Airflow"
    exit 1
fi

# Print info
echo "Deploying Airflow to namespace: $NAMESPACE"

# Delete existing resources
echo "Cleaning up existing resources..."
kubectl delete deployment postgres redis --namespace $NAMESPACE --ignore-not-found
kubectl delete service postgres redis --namespace $NAMESPACE --ignore-not-found
kubectl delete pvc postgres-pvc --namespace $NAMESPACE --ignore-not-found

# Delete existing Helm release
echo "Deleting existing Airflow Helm release..."
helm delete airflow --namespace $NAMESPACE --ignore-not-found

# Add the official Apache Airflow Helm repository
helm repo add apache-airflow https://airflow.apache.org
helm repo update

# Install/Upgrade Airflow with minimal permissions required
helm upgrade --install airflow apache-airflow/airflow \
    --namespace $NAMESPACE \
    --set webserver.service.type=ClusterIP \
    --set ingress.enabled=true \
    --set ingress.web.host=airflow.nrp-nautilus.io \
    --set ingress.web.ingressClassName=haproxy \
    --set dags.persistence.enabled=true \
    --set dags.gitSync.enabled=false \
    --set executor=LocalExecutor \
    --set postgresql.enabled=true \
    --set redis.enabled=false \
    --set webserver.defaultUser.enabled=true \
    --set webserver.defaultUser.username=admin \
    --set webserver.defaultUser.password=admin \
    --set rbac.create=false \
    --set serviceAccount.create=false \
    --set "webserver.resources.requests.cpu=500m" \
    --set "webserver.resources.requests.memory=1Gi" \
    --set "webserver.resources.limits.cpu=1000m" \
    --set "webserver.resources.limits.memory=2Gi" \
    --set "scheduler.resources.requests.cpu=500m" \
    --set "scheduler.resources.requests.memory=1Gi" \
    --set "scheduler.resources.limits.cpu=1000m" \
    --set "scheduler.resources.limits.memory=2Gi" \
    --set "statsd.resources.requests.cpu=100m" \
    --set "statsd.resources.requests.memory=256Mi" \
    --set "statsd.resources.limits.cpu=200m" \
    --set "statsd.resources.limits.memory=512Mi" \
    --set "migrateDatabaseJob.resources.requests.cpu=200m" \
    --set "migrateDatabaseJob.resources.requests.memory=512Mi" \
    --set "migrateDatabaseJob.resources.limits.cpu=400m" \
    --set "migrateDatabaseJob.resources.limits.memory=1Gi" \
    --set "logs.persistence.enabled=true" \
    --set "logs.persistence.size=1Gi"

echo "Airflow deployment completed successfully!"
echo "You can access the Airflow UI at: https://airflow.nrp-nautilus.io"
