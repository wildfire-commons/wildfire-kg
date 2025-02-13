#!/bin/bash

ENV=$1
COMPONENT=$2

if [ -z "$ENV" ] || [ -z "$COMPONENT" ]; then
    echo "Usage: ./deploy.sh <environment> <component>"
    echo "Environments: dev, prod"
    echo "Components: airflow, graphdb, all"
    exit 1
fi

# Get the project root directory (one level up from scripts/)
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

NAMESPACE="wifire-kg"          # Dev namespace
if [ "$ENV" = "prod" ]; then
    NAMESPACE="wifire-kg-prod" # Prod namespace
fi

# Function to add helm repo if it doesn't exist
add_helm_repo() {
    local repo_name=$1
    local repo_url=$2
    
    if ! helm repo list | grep -q "^${repo_name}"; then
        echo "Adding ${repo_name} helm repository..."
        helm repo add $repo_name $repo_url
        helm repo update $repo_name
    fi
}

deploy_component() {
    local component=$1
    local chart=$2
    
    # Add required repo based on component
    case $component in
        "airflow")
            add_helm_repo "apache-airflow" "https://airflow.apache.org"
            ;;
        "graphdb")
            add_helm_repo "ontotext" "https://maven.ontotext.com/repository/helm-public/"
            ;;
    esac
    
    echo "Deploying $component to $ENV environment..."
    helm upgrade --install $component $chart \
        --namespace $NAMESPACE \
        --values "${PROJECT_ROOT}/iac/helm/values/${ENV}/${component}-values.yaml"
}

case $COMPONENT in
    "all")
        deploy_component "airflow" "apache-airflow/airflow"
        deploy_component "graphdb" "ontotext/graphdb"
        ;;
    "airflow")
        deploy_component "airflow" "apache-airflow/airflow"
        ;;
    "graphdb")
        deploy_component "graphdb" "ontotext/graphdb"
        ;;
    *)
        echo "Invalid component. Use: airflow, graphdb, or all"
        exit 1
        ;;
esac 