#!/bin/bash

# Default to production environment
ENV=${1:-prod}

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies based on environment
case "$ENV" in
  prod|production)
    echo "Installing production dependencies and building wildfire-kg-api package..."
    pip install .
    ;;
  dev|development)
    echo "Installing development dependencies (includes production)..."
    # This installs both production dependencies and development extras
    pip install -e ".[dev]"
    ;;
  *)
    echo "Unknown environment: $ENV"
    echo "Usage: source setup.sh [dev|prod]"
    exit 1
    ;;
esac

echo "Setup complete!"
echo "Don't forget to add your API keys to the .env file."
echo "Run 'wkg run' to start the API server in production mode."
echo "Run 'wkg run --dev' to start the API server in development mode."
echo "Run 'wkg studio' to start the API server in studio mode."