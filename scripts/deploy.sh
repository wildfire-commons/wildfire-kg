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
VALID_COMPONENTS=("graphdb" "airflow" "langgraph" "frontend" "supabase")

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

# Function to handle secrets and environment variables
handle_secrets() {
    local manifest_path=$1
    local temp_manifest=$(mktemp)
    
    # Function to get and encode secret value
    get_secret_value() {
        local secret_name=$1
        local value
        
        # First try to get from environment variable
        value="${!secret_name}"
        
        # If not found and .env file exists, try to get from .env
        if [ -z "$value" ] && [ -f "${PROJECT_ROOT}/.env" ]; then
            # Use awk to handle values with special characters
            value=$(awk -F= -v key="^${secret_name}=" '$0 ~ key {print $2}' "${PROJECT_ROOT}/.env" | xargs)
        fi
        
        # If still not found, return empty
        if [ -z "$value" ]; then
            echo "Error: Empty value for $secret_name in .env" >&2
            exit 1
        fi
        echo -n "$value" | base64 | tr -d '\n'
    }
    
    # Process each line of the manifest
    while IFS= read -r line; do
        if [[ $line =~ \$\{([A-Z_]+)\} ]]; then
            secret_name="${BASH_REMATCH[1]}"
            encoded_value=$(get_secret_value "$secret_name")
            
            echo "DEBUG: Processing ${secret_name} -> Raw: '${value}' | Encoded: '${encoded_value}'" >&2
            
            if [ -z "$encoded_value" ]; then
                echo "Warning: Secret $secret_name not found in environment or .env file"
                echo "$line" >> "$temp_manifest"
            else
                # Replace placeholder with encoded value
                echo "$line" | sed "s/\${$secret_name}/$encoded_value/" >> "$temp_manifest"
            fi
        else
            echo "$line" >> "$temp_manifest"
        fi
    done < "$manifest_path"
    
    echo "$temp_manifest"
}

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
    local clean=$2
    local namespace="wifire-kg"
    local registry="gitlab-registry.nrp-nautilus.io"
    local image_name="wildfire-kg/wildfire-kg"
    local image_tag="langgraph-${env}"
    local full_image_name="${registry}/${image_name}:${image_tag}"
    local api_dir="${PROJECT_ROOT}/applications/wildfire-kg-api"

    echo "Deploying LangGraph to ${env} environment..."

    # Check if GitLab credentials are set
    if [ -z "$GITLAB_USER" ] || [ -z "$GITLAB_PASSWORD" ]; then
        echo "Error: GitLab credentials not found. Please set GITLAB_USER and GITLAB_PASSWORD in .env file"
        exit 1
    fi

    # Check if the API directory exists
    if [ ! -d "$api_dir" ]; then
        echo "Error: LangGraph API directory not found at $api_dir"
        exit 1
    fi

    # Change to the API directory
    cd "$api_dir"

    # Login to GitLab registry
    echo "Logging in to GitLab registry..."
    echo "$GITLAB_PASSWORD" | docker login ${registry} -u $GITLAB_USER --password-stdin

    # Build the Docker image for x86_64 platform
    echo "Building LangGraph image for x86_64 platform..."
    docker buildx build --platform linux/amd64 -t ${full_image_name} --build-arg PYTHON_ENV=production --push .

    # Check if the build was successful
    if [ $? -ne 0 ]; then
        echo "Error: LangGraph image build failed"
        cd "${PROJECT_ROOT}"
        exit 1
    fi

    # Return to the project root
    cd "${PROJECT_ROOT}"

    # Handle langgraph secrets and environment substitution
    local langgraph_secrets_manifest_path="${PROJECT_ROOT}/iac/manifests/langgraph-secrets.yaml"
    local langgraph_secrets_manifest=$(handle_secrets "$langgraph_secrets_manifest_path")
    
    echo "Generated secrets manifest contents:"
    cat "$langgraph_secrets_manifest"
    
    # Force delete and recreate secrets
    echo "Deleting existing langgraph-secrets..."
    kubectl delete secret langgraph-secrets --namespace $NAMESPACE --ignore-not-found
    sleep 2  # Wait for secret to be fully removed
    
    echo "Creating fresh langgraph-secrets..."
    kubectl apply -f "$langgraph_secrets_manifest"
    
    # Verify secret creation
    if ! kubectl get secret langgraph-secrets --namespace $NAMESPACE > /dev/null 2>&1; then
        echo "Error: Failed to recreate langgraph-secrets"
        exit 1
    fi

    # Handle secrets and environment substitution
    local manifest_path="${PROJECT_ROOT}/iac/manifests/langgraph.yaml"
    local temp_manifest=$(handle_secrets "$manifest_path")
    
    # Replace ENV_PLACEHOLDER with the actual environment
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS requires an empty string for -i
        sed -i '' "s/ENV_PLACEHOLDER/${env}/g" "${temp_manifest}"
        
        # For production, update the host to remove the environment prefix
        if [ "$env" = "prod" ]; then
            sed -i '' 's/langgraph-prod.nrp-nautilus.io/langgraph.nrp-nautilus.io/g' "${temp_manifest}"
        fi
    else
        # Linux version
        sed -i "s/ENV_PLACEHOLDER/${env}/g" "${temp_manifest}"
        
        # For production, update the host to remove the environment prefix
        if [ "$env" = "prod" ]; then
            sed -i 's/langgraph-prod.nrp-nautilus.io/langgraph.nrp-nautilus.io/g' "${temp_manifest}"
        fi
    fi

    # Apply the manifest
    if [ "$clean" = true ]; then
        echo "Cleaning up existing LangGraph deployment..."
        kubectl delete -f "${temp_manifest}" --ignore-not-found=true
        sleep 5
    fi

    echo "Applying LangGraph manifest..."
    kubectl apply -f "${temp_manifest}"

    # Wait for deployment to be ready
    echo "Waiting for LangGraph deployment to be ready..."
    kubectl rollout status deployment/langgraph -n ${namespace} --timeout=300s

    if [ $? -ne 0 ]; then
        echo "Error: LangGraph deployment failed to become ready"
        echo "Checking pod status..."
        kubectl get pods -n ${namespace} -l app=langgraph
        echo "Checking pod logs..."
        kubectl logs -n ${namespace} -l app=langgraph --tail=50
        cd "${PROJECT_ROOT}"
        exit 1
    fi

    # Clean up temporary file
    rm "${temp_manifest}"

    echo "LangGraph deployment completed and ready!"
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
    
    # Clean up existing deployment if --clean flag is set
    if [ "$CLEAN" = true ]; then
        echo "Cleaning up existing frontend deployment..."
        kubectl delete deployment wildfire-kg-frontend-${env} --namespace $NAMESPACE --ignore-not-found
        kubectl delete service wildfire-kg-frontend-${env} --namespace $NAMESPACE --ignore-not-found
        kubectl delete ingress wildfire-kg-frontend-${env} --namespace $NAMESPACE --ignore-not-found
        
        # Wait for resources to be cleaned up
        echo "Waiting for resources to be cleaned up..."
        sleep 5
    fi
    
    # Handle frontend secrets and environment substitution
    # local frontend_secrets_manifest_path="${PROJECT_ROOT}/iac/manifests/frontend-secrets.yaml"
    # local frontend_secrets_manifest=$(handle_secrets "$frontend_secrets_manifest_path")
    # kubectl apply -f "$frontend_secrets_manifest"
    # rm "$frontend_secrets_manifest"
    # # Optionally verify frontend-secrets exists
    # if ! kubectl get secret frontend-secrets --namespace $NAMESPACE > /dev/null 2>&1; then
    #     echo "Error: frontend-secrets secret was not created successfully in namespace $NAMESPACE. Aborting frontend deployment."
    #     exit 1
    # fi
    
    # Create a temporary file with environment-specific values
    TEMP_MANIFEST=$(mktemp)
    cat "${PROJECT_ROOT}/iac/manifests/frontend.yaml" | sed "s/ENV_PLACEHOLDER/${env}/g" > "$TEMP_MANIFEST"
    
    # For production, update the host to remove the environment prefix
    if [ "$env" = "prod" ]; then
        sed -i '' 's/wildfire-prod.nrp-nautilus.io/wildfire.nrp-nautilus.io/g' "$TEMP_MANIFEST"
    fi
    
    # Deploy frontend
    echo "Deploying frontend..."
    kubectl apply -f "$TEMP_MANIFEST"
    
    # Clean up temporary file
    rm "$TEMP_MANIFEST"
    
    # Wait for deployment to be ready
    echo "Waiting for frontend deployment to be ready..."
    kubectl wait --for=condition=available deployment/wildfire-kg-frontend-${env} --namespace $NAMESPACE --timeout=300s
    
    # Check frontend ingress status
    echo "Checking frontend ingress status..."
    kubectl get ingress wildfire-kg-frontend-${env} --namespace $NAMESPACE
    
    # Set the correct URL based on environment
    local url
    if [ "$env" = "prod" ]; then
        url="https://wildfire.nrp-nautilus.io"
    else
        url="https://wildfire-${env}.nrp-nautilus.io"
    fi
    
    echo "Frontend deployment completed successfully!"
    echo "You can access the frontend at: ${url}"
}

# Function to deploy supabase
deploy_supabase() {
    local env=$1
    
    echo "Deploying Supabase for $env environment..."
    
    # Clean up existing deployment if --clean flag is set
    if [ "$CLEAN" = true ]; then
        echo "Cleaning up existing Supabase deployment..."
        kubectl delete deployment supabase-db --namespace $NAMESPACE --ignore-not-found
        kubectl delete deployment supabase-auth --namespace $NAMESPACE --ignore-not-found
        kubectl delete deployment supabase-storage --namespace $NAMESPACE --ignore-not-found
        kubectl delete service supabase-db --namespace $NAMESPACE --ignore-not-found
        kubectl delete service supabase-auth --namespace $NAMESPACE --ignore-not-found
        kubectl delete service supabase-storage --namespace $NAMESPACE --ignore-not-found
        kubectl delete ingress supabase-ingress --namespace $NAMESPACE --ignore-not-found
        kubectl delete pvc supabase-db-pvc --namespace $NAMESPACE --ignore-not-found
        kubectl delete pvc supabase-storage-pvc --namespace $NAMESPACE --ignore-not-found
        kubectl delete secret supabase-secrets --namespace $NAMESPACE --ignore-not-found
        
        # Wait for resources to be cleaned up
        echo "Waiting for resources to be cleaned up..."
        sleep 5
    fi
    
    # Handle secrets and environment substitution
    local supabase_secrets_manifest_path="${PROJECT_ROOT}/iac/manifests/supabase-secrets.yaml"
    local manifest_path="${PROJECT_ROOT}/iac/manifests/supabase.yaml"
    local temp_manifest=$(handle_secrets "$manifest_path")
    
    # Replace environment placeholders
    sed -i "s/ENV_PLACEHOLDER/${env}/g" "$temp_manifest"
    
    # For production, update the host to remove the environment prefix
    if [ "$env" = "prod" ]; then
        sed -i 's/supabase-prod.nrp-nautilus.io/supabase.nrp-nautilus.io/g' "$temp_manifest"
        sed -i 's/wildfire-prod.nrp-nautilus.io/wildfire.nrp-nautilus.io/g' "$temp_manifest"
    fi
    
    # Deploy Supabase
    echo "Deploying Supabase..."
    kubectl apply -f "$temp_manifest"
    
    # Wait for deployments to be ready
    echo "Waiting for Supabase deployments to be ready..."
    kubectl wait --for=condition=available deployment/supabase-db --namespace $NAMESPACE --timeout=300s
    kubectl wait --for=condition=available deployment/supabase-auth --namespace $NAMESPACE --timeout=300s
    kubectl wait --for=condition=available deployment/supabase-storage --namespace $NAMESPACE --timeout=300s
    
    # Check ingress status
    echo "Checking Supabase ingress status..."
    kubectl get ingress supabase-ingress --namespace $NAMESPACE
    
    # Set the correct URL based on environment
    local url
    if [ "$env" = "prod" ]; then
        url="https://supabase.nrp-nautilus.io"
    else
        url="https://supabase-${env}.nrp-nautilus.io"
    fi
    
    # Clean up temporary file
    rm "$temp_manifest"
    
    echo "Supabase deployment completed successfully!"
    echo "You can access Supabase at: ${url}"
    echo "Auth endpoint: ${url}/auth"
    echo "Storage endpoint: ${url}/storage"
}

case $COMPONENT in
    "airflow")
        deploy_component "airflow"
        ;;
    "graphdb")
        deploy_component "graphdb"
        ;;
    "langgraph")
        deploy_langgraph "$ENV" "$CLEAN"
        ;;
    "frontend")
        deploy_frontend "$ENV"
        ;;
    "supabase")
        deploy_supabase "$ENV"
        ;;
    *)
        echo "Invalid component. Valid components: ${VALID_COMPONENTS[*]}"
        exit 1
        ;;
esac 