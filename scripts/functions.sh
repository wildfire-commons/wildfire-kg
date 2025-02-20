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

# Export the function after it's defined
export -f deploy 