#!/bin/bash

ENV=$1
COMPONENT=$2
CLEAN=false
NO_HOOKS=""

# Parse additional flags
while [[ $# -gt 2 ]]; do
    case "$3" in
        --clean)
            CLEAN=true
            ;;
        --no-hooks)
            NO_HOOKS="--no-hooks"
            ;;
        *)
            echo "Unknown option: $3"
            exit 1
            ;;
    esac
    shift
done

# Valid component names
VALID_ENVIRONMENTS=("dev" "prod")
VALID_COMPONENTS=("graphdb" "airflow" "neo4j")

# Function to validate component name
validate_component() {
    local component=$1
    for valid in "${VALID_COMPONENTS[@]}"; do
        if [ "$component" = "$valid" ]; then
            return 0
        fi
    done
    echo "Error: Invalid component '$component'"
    echo "Valid components: ${VALID_COMPONENTS[*]}"
    exit 1
}

# Check if the environment and component are provided
if [ -z "$ENV" ] || [ -z "$COMPONENT" ]; then
    echo "Usage: ./deploy.sh <environment> <component>"
    echo "Examples:"
    echo "  ./deploy.sh dev graphdb    # Deploys as graphdb-dev"
    echo "  ./deploy.sh prod graphdb   # Deploys as graphdb-prod"
    echo "Environments: ${VALID_ENVIRONMENTS[*]}"
    echo "Components: ${VALID_COMPONENTS[*]}"
    exit 1
fi

# Validate component name before proceeding
validate_component "$COMPONENT"

# Get the project root directory (one level up from scripts/)
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

# Currently, we only have one namespace for all environments
NAMESPACE="wifire-kg"
# if [ "$ENV" = "prod" ]; then
#     NAMESPACE="wifire-kg-prod" # Prod namespace
# fi

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

# Function to deploy a component
deploy_component() {
    local component=$1
    local chart=$2
    local release_name="${component}-${ENV}"
    
    # Clean up existing release if --clean flag is set
    if [ "$CLEAN" = true ]; then
        echo "Cleaning up existing release $release_name..."
        helm uninstall $release_name --namespace $NAMESPACE ${NO_HOOKS:-} || true
        # Wait for resources to be cleaned up
        sleep 5
    fi
    
    # Add required repo based on component
    case $component in
        "airflow")
            add_helm_repo "apache-airflow" "https://airflow.apache.org"
            chart="apache-airflow/airflow"
            ;;
        "graphdb")
            add_helm_repo "ontotext" "https://maven.ontotext.com/repository/helm-public/"
            chart="ontotext/graphdb"
            ;;
        "neo4j")
            add_helm_repo "neo4j" "https://helm.neo4j.com/neo4j"
            chart="neo4j/neo4j"
            ;;
    esac
    
    echo "Deploying $release_name to $NAMESPACE namespace..."
    helm upgrade --install $release_name $chart \
        --namespace $NAMESPACE \
        --values "${PROJECT_ROOT}/iac/helm/values/${ENV}/${component}.${ENV}.values.yaml"
}

case $COMPONENT in
    "airflow")
        deploy_component "airflow"
        ;;
    "graphdb")
        deploy_component "graphdb"
        ;;
    "neo4j")
        deploy_component "neo4j"
        ;;
    *)
        echo "Invalid component. Valid components: ${VALID_COMPONENTS[*]}"
        exit 1
        ;;
esac 