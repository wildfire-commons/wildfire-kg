#!/bin/bash

# Default to production environment
ENV=${1:-prod}

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install dependencies based on environment
case "$ENV" in
  prod|production)
    echo "Installing production dependencies..."
    pip install -e .
    ;;
  dev|development)
    echo "Installing development dependencies..."
    pip install -e ".[dev]"
    ;;
  *)
    echo "Unknown environment: $ENV"
    echo "Usage: ./setup.sh [dev|prod]"
    exit 1
    ;;
esac

# Create a .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    echo "OPENAI_API_KEY=" > .env
    echo "NEO4J_URI=bolt://localhost:7687" >> .env
    echo "NEO4J_USER=neo4j" >> .env
    echo "NEO4J_PASSWORD=password" >> .env
    echo "TAVILY_API_KEY=" >> .env
fi

echo "Setup complete! Don't forget to add your API keys to the .env file."
echo "Run './run.sh' to start the API server."