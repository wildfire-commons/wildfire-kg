#!/bin/bash

# Default values
ENV="development"
COMPONENT="app"

# Help function
show_help() {
    echo "Usage: ./run.sh [options] [component]"
    echo "Components:"
    echo "  app      Run the frontend and backend (default)"
    echo "  airflow  Run the Airflow stack"
    echo "  all      Run everything"
    echo ""
    echo "Options:"
    echo "  -e, --env     Set environment (development/production) [default: development]"
    echo "  -b, --build   Force rebuild of containers"
    echo "  -d, --down    Stop and remove containers"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run.sh app              # Run app in development mode"
    echo "  ./run.sh airflow          # Run Airflow in development mode"
    echo "  ./run.sh all -e prod      # Run everything in production mode"
    echo "  ./run.sh app -b           # Rebuild and run app"
    echo "  ./run.sh airflow -d       # Stop Airflow containers"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        app|airflow|all)
            COMPONENT="$1"
            shift
            ;;
        -e|--env)
            ENV="$2"
            shift 2
            ;;
        -b|--build)
            BUILD=true
            shift
            ;;
        -d|--down)
            DOWN=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set environment variables based on environment
if [ "$ENV" = "production" ]; then
    export NODE_ENV=production
    export PYTHON_ENV=production
    export DEV_MOUNT=" "
else
    export NODE_ENV=development
    export PYTHON_ENV=development
    export DEV_MOUNT=""
    export WATCHPACK_POLLING=true
fi

# Function to handle docker compose commands
run_compose() {
    local compose_files="-f $1"
    if [ "$DOWN" = true ]; then
        docker compose $compose_files down
    elif [ "$BUILD" = true ]; then
        docker compose $compose_files up --build
    else
        docker compose $compose_files up
    fi
}

# Execute based on component
case $COMPONENT in
    "app")
        run_compose "docker-compose.app.yaml"
        ;;
    "airflow")
        run_compose "docker-compose.airflow.yaml"
        ;;
    "all")
        if [ "$DOWN" = true ]; then
            docker compose -f docker-compose.app.yaml -f docker-compose.airflow.yaml down
        elif [ "$BUILD" = true ]; then
            docker compose -f docker-compose.app.yaml -f docker-compose.airflow.yaml up --build
        else
            docker compose -f docker-compose.app.yaml -f docker-compose.airflow.yaml up
        fi
        ;;
esac 