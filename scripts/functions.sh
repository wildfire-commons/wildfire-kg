#!/bin/bash

function deploy() {
    # Get absolute path to deploy.sh in the scripts directory
    local deploy_script="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/deploy.sh"
    
    # If we're in the project root, look in scripts/
    if [[ ! -f "${deploy_script}" ]]; then
        deploy_script="$(pwd)/scripts/deploy.sh"
    fi
    
    # Execute deploy.sh with absolute path
    bash "${deploy_script}" "$@"
}

function build_langgraph() {
    # Get the project root directory
    local project_root="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
    
    # Default to development environment if not specified
    local env=${1:-dev}
    
    echo "Building LangGraph application for $env environment..."
    
    # Navigate to the LangGraph API directory
    cd "${project_root}/applications/wildfire-kg-api"
    
    # Ensure we have a virtual environment
    if [[ ! -d "venv" ]]; then
        echo "Creating virtual environment..."
        python -m venv venv
    fi
    
    # Activate the virtual environment
    source venv/bin/activate
    
    # Ensure development dependencies are installed
    echo "Installing development dependencies..."
    pip install -e ".[dev]"
    
    # Build the LangGraph application
    echo "Building LangGraph application..."
    langgraph build
    
    # Create a ConfigMap with the langgraph.json content
    echo "Creating ConfigMap for LangGraph configuration..."
    kubectl create configmap langgraph-config \
        --namespace wifire-kg \
        --from-file=langgraph.json \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Deactivate the virtual environment
    deactivate
    
    # Return to the original directory
    cd - > /dev/null
    
    echo "LangGraph build completed successfully!"
    echo "Now you can deploy the LangGraph server using: kubectl apply -f ${project_root}/iac/manifests/langgraph.yaml"
}

# Export the functions after they're defined
export -f deploy
export -f build_langgraph
