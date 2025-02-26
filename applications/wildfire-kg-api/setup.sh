#!/bin/bash

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the API (for development)
uvicorn src.api:app --reload --port 8000 --reload-dir src 