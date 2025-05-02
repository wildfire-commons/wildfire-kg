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
VALID_COMPONENTS=("graphdb" "airflow" "langgraph" "frontend")

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
    echo "  ./deploy.sh dev langgraph  # Deploys LangGraph server"
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

# Load environment variables from .env file
if [ -f "${PROJECT_ROOT}/.env" ]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' "${PROJECT_ROOT}/.env" | xargs)
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

# Function to deploy LangGraph
deploy_langgraph() {
    local env=$1
    
    echo "Building and deploying LangGraph for $env environment..."
    
    # Navigate to the LangGraph API directory
    cd "${PROJECT_ROOT}/applications/wildfire-kg-api"
    
    # Create a virtual environment if it doesn't exist
    if [[ ! -d "venv" ]]; then
        echo "Creating virtual environment..."
        python -m venv venv
    fi
    
    # Activate the virtual environment
    source venv/bin/activate
    
    # Install development dependencies
    echo "Installing development dependencies..."
    pip install -e ".[dev]"
    
    # Build the LangGraph application
    echo "Building LangGraph application..."
    langgraph build
    
    # Create a ConfigMap with the langgraph.json content
    echo "Creating ConfigMap for LangGraph configuration..."
    kubectl create configmap langgraph-config \
        --namespace $NAMESPACE \
        --from-file=langgraph.json \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Deactivate the virtual environment
    deactivate
    
    # Return to the project root
    cd "${PROJECT_ROOT}"
    
    # Clean up existing deployment if --clean flag is set
    if [ "$CLEAN" = true ]; then
        echo "Cleaning up existing LangGraph deployment..."
        kubectl delete deployment langgraph --namespace $NAMESPACE --ignore-not-found
        kubectl delete service langgraph --namespace $NAMESPACE --ignore-not-found
        kubectl delete ingress langgraph-ingress --namespace $NAMESPACE --ignore-not-found
        
        # Wait for resources to be cleaned up
        echo "Waiting for resources to be cleaned up..."
        sleep 5
    fi
    
    # Create a temporary file with environment-specific values
    TEMP_MANIFEST=$(mktemp)
    cat "${PROJECT_ROOT}/iac/manifests/langgraph.yaml" | sed "s/ENV_PLACEHOLDER/${env}/g" > "$TEMP_MANIFEST"
    
    # Deploy LangGraph
    echo "Deploying LangGraph server..."
    kubectl apply -f "$TEMP_MANIFEST"
    
    # Clean up temporary file
    rm "$TEMP_MANIFEST"
    
    # Wait for deployment to be ready
    echo "Waiting for LangGraph deployment to be ready..."
    kubectl wait --for=condition=Available=True deployment/langgraph -n $NAMESPACE --timeout=300s
    
    echo "LangGraph deployment completed successfully!"
    echo "You can access the LangGraph server at: https://langgraph-${env}-wifire-kg.nrp-nautilus.io"
}

# Function to deploy a component
deploy_component() {
    local component=$1
    local chart=$2
    local release_name="${component}-${ENV}"
    
    # Clean up existing release if --clean flag is set (skip for airflow)
    if [ "$CLEAN" = true ] && [ "$component" != "airflow" ]; then
        echo "Cleaning up existing release $release_name..."
        helm uninstall $release_name --namespace $NAMESPACE ${NO_HOOKS:-} || true
        # Wait for resources to be cleaned up
        sleep 5
    fi
    
    # Add required repo based on component
    case $component in
        "airflow")
            echo "Deploying Airflow using manifests..."
            
            # Delete existing resources if --clean flag is set
            if [ "$CLEAN" = true ]; then
                echo "Cleaning up existing Airflow resources..."
                kubectl delete deployment postgres redis airflow-webserver airflow-scheduler airflow-worker --namespace $NAMESPACE --ignore-not-found
                kubectl delete service postgres redis airflow-webserver --namespace $NAMESPACE --ignore-not-found
                kubectl delete configmap airflow-config --namespace $NAMESPACE --ignore-not-found
                kubectl delete ingress airflow-ingress --namespace $NAMESPACE --ignore-not-found
                
                # Wait for resources to be cleaned up
                echo "Waiting for resources to be cleaned up..."
                sleep 5
            fi
            
            # Deploy Redis and Postgres first
            echo "Deploying Redis and Postgres..."
            kubectl apply -f ${PROJECT_ROOT}/iac/manifests/airflow/airflow.redis.yaml
            kubectl apply -f ${PROJECT_ROOT}/iac/manifests/airflow/airflow.postgres.yaml
            
            # Wait for Redis and Postgres to be ready
            echo "Waiting for Redis and Postgres deployments to be ready..."
            kubectl wait --for=condition=Available=True deployment/redis -n $NAMESPACE --timeout=300s
            kubectl wait --for=condition=Available=True deployment/postgres -n $NAMESPACE --timeout=300s
            
            # Deploy main Airflow configuration
            echo "Deploying Airflow components..."
            kubectl apply -f ${PROJECT_ROOT}/iac/manifests/airflow/airflow.yaml
            
            # Wait for Airflow deployments to be ready
            echo "Waiting for Airflow components..."
            kubectl wait --for=condition=Available=True deployment/airflow-webserver -n $NAMESPACE --timeout=300s
            kubectl wait --for=condition=Available=True deployment/airflow-scheduler -n $NAMESPACE --timeout=300s
            kubectl wait --for=condition=Available=True deployment/airflow-worker -n $NAMESPACE --timeout=300s
            
            echo "Airflow deployment completed successfully!"
            echo "You can access the Airflow UI at: https://wifire-kg-airflow.nrp-nautilus.io"
            ;;
        "graphdb")
            add_helm_repo "ontotext" "https://maven.ontotext.com/repository/helm-public/"
            chart="ontotext/graphdb"
            ;;
    esac
    
    echo "Deploying $release_name to $NAMESPACE namespace..."
    helm upgrade --install $release_name $chart \
        --namespace $NAMESPACE \
        --values "${PROJECT_ROOT}/iac/helm/values/${ENV}/${component}.${ENV}.values.yaml"
}

# Function to deploy frontend
deploy_frontend() {
    local env=$1
    
    # Check if GitLab credentials are set
    if [ -z "$GITLAB_USER" ] || [ -z "$GITLAB_PASSWORD" ]; then
        echo "Error: GitLab credentials not found. Please set GITLAB_USER and GITLAB_PASSWORD in .env file"
        exit 1
    fi
    
    echo "Building and deploying frontend for $env environment..."
    
    # Navigate to the frontend directory
    cd "${PROJECT_ROOT}/applications/wildfire-kg-frontend"
    
    # Login to GitLab registry
    echo "Logging in to GitLab registry..."
    echo "$GITLAB_PASSWORD" | docker login gitlab-registry.nrp-nautilus.io -u $GITLAB_USER --password-stdin
    
    # Build the frontend Docker image with proper registry path and platform
    echo "Building frontend Docker image..."
    docker build --platform linux/amd64 -t gitlab-registry.nrp-nautilus.io/wildfire-kg/wildfire-kg:frontend .
    
    # Push the image to GitLab registry
    echo "Pushing frontend Docker image..."
    docker push gitlab-registry.nrp-nautilus.io/wildfire-kg/wildfire-kg:frontend
    
    # Clean up existing deployment if --clean flag is set
    if [ "$CLEAN" = true ]; then
        echo "Cleaning up existing frontend deployment..."
        kubectl delete deployment wildfire-kg-frontend --namespace $NAMESPACE --ignore-not-found
        kubectl delete service wildfire-kg-frontend --namespace $NAMESPACE --ignore-not-found
        kubectl delete ingress wildfire-kg-frontend --namespace $NAMESPACE --ignore-not-found
        
        # Wait for resources to be cleaned up
        echo "Waiting for resources to be cleaned up..."
        sleep 5
    fi
    
    # Create a temporary file with environment-specific values
    TEMP_MANIFEST=$(mktemp)
    cat "${PROJECT_ROOT}/iac/manifests/frontend.yaml" | sed "s/ENV_PLACEHOLDER/${env}/g" > "$TEMP_MANIFEST"
    
    # Deploy frontend
    echo "Deploying frontend..."
    kubectl apply -f "$TEMP_MANIFEST"
    
    # Clean up temporary file
    rm "$TEMP_MANIFEST"
    
    # Wait for deployment to be ready
    echo "Waiting for frontend deployment to be ready..."
    kubectl wait --for=condition=available deployment/wildfire-kg-frontend --namespace $NAMESPACE --timeout=300s
    
    # Check frontend ingress status
    echo "Checking frontend ingress status..."
    kubectl get ingress wildfire-kg-frontend --namespace $NAMESPACE
    
    echo "Frontend deployment completed successfully!"
    echo "You can access the frontend at: https://wildfire-${env}.nrp-nautilus.io"
}

case $COMPONENT in
    "airflow")
        deploy_component "airflow"
        ;;
    "graphdb")
        deploy_component "graphdb"
        ;;
    "langgraph")
        deploy_langgraph "$ENV"
        ;;
    "frontend")
        deploy_frontend "$ENV"
        ;;
    *)
        echo "Invalid component. Valid components: ${VALID_COMPONENTS[*]}"
        exit 1
        ;;
esac 