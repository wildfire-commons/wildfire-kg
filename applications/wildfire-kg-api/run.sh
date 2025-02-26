#!/bin/bash

# Activate the virtual environment
source venv/bin/activate

# Check command line arguments
case "$1" in
  dev|--dev|-d)
    echo "Starting server in development mode (with auto-reload)..."
    python -m src.main dev
    ;;
  studio|--studio|-s)
    echo "Starting LangGraph Studio server..."
    python -m src.main studio
    ;;
  help|--help|-h)
    python -m src.main --help
    ;;
  *)
    echo "Starting server in production mode..."
    python -m src.main run
    ;;
esac 