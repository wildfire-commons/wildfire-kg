# Wildfire Knowledge Graph API

This API provides access to the wildfire knowledge graph and includes a conversational AI interface powered by LangGraph.

## Features

- Knowledge graph querying with natural language
- Conversational AI interface using LangGraph
- Integration with external data sources through RAG
- LangGraph Studio support for visualization and debugging
- Streamlit app for easier query configuration management and testing during local development
- Health check endpoints for monitoring
- S3 integration for data storage

## Setup

1. Clone the repository
2. Run the setup script with the desired environment:

```bash
cd wildfire-kg-api
source setup.sh dev # or source setup.sh prod
```

3. Copy the example environment file and update it with your credentials:
  
```bash
cp .env.example .env
# Edit .env with your credentials
```

## Usage

### Command Line Interface

The API comes with a convenient command-line interface:

```bash
# Show available commands
wkg-api --help

# Run the API server
wkg-api run

# Run in development mode with auto-reload
wkg-api run --dev
```

### LangGraph Studio

With the LangGraph integration, you can use LangGraph Studio for development:
> [!NOTE]
> You must have the dev dependencies installed to use LangGraph Studio.

```bash
# Start LangGraph Studio
langgraph dev
```

This will:
1. Start a local development server
2. Open LangGraph Studio in your browser
3. Allow you to visualize and debug your conversation graph
4. Provide access to your API endpoints

You can trace graph executions, inspect state at each node, and test your graph interactively.

## Streamlit App

The API includes a Streamlit app for test configuration management and development.

```bash
# Make sure you have the dev dependencies installed
pip install -e '.[dev]'

# Start the Streamlit app
wkg-api ui
```

This will launch the Test Configuration Manager UI, which allows you to:
- View, edit, and delete saved test configurations
- Create new test configurations
- Send configurations directly to the LangGraph Studio
- Check the status of your LangGraph server

The testing tools are organized in a dedicated directory structure:
```
tests/
├── streamlit/           # Streamlit app directory
│   └── app.py           # Main Streamlit application
├── utils/               # Shared utility modules
│   └── test_config_manager.py  # Configuration management utilities
├── performance/         # Performance testing utilities
│   └── run_performance_tests.py  # Script for running performance tests
├── test_configs/        # Directory for saved test configurations
└── README.md            # This file
```

More information can be found in the [tests/README.md](tests/README.md) file.

### API Endpoints

The API provides several endpoints:

- **Health Checks**:
  - `GET /health` - Main health check endpoint
  - `GET /health/ping` - Simple ping endpoint
  - `GET /health/ready` - Kubernetes-style readiness probe

- **S3 Storage**:
  - `GET /api/storage/buckets` - List S3 buckets
  - `GET /api/storage/buckets/{bucket_name}/objects` - List objects in a bucket
  - `POST /api/storage/buckets/{bucket_name}/folders` - Create a folder
  - `DELETE /api/storage/buckets/{bucket_name}/folders` - Delete a folder

## Deployment

TODO: Verify deployment instructions

## Project Structure

```
wildfire-kg-api/
├── src/                        # Main source code
│   ├── __init__.py             # Package initialization
│   ├── app.py                  # FastAPI application
│   ├── main.py                 # CLI and entry points
│   ├── routes/                 # API routes
│   │   ├── __init__.py         # Route registration system
│   │   ├── health.py           # Health check endpoints
│   │   └── s3.py               # S3 storage endpoints
│   └── orchestration/          # LangGraph orchestration
│       ├── agents/             # Agents for routing queries and generating responses
│       ├── graph/              # LangGraph workflow definitions and orchestration logic
│       ├── state/              # Conversation state management and data models
│       └── tools/              # Knowledge graph and RAG tools for retrieving information
├── tests/                      # Test suite
│   ├── streamlit/              # Streamlit app for test configuration management
│   ├── utils/                  # Shared utility modules
│   └── performance/            # Performance testing utilities
├── .env.example                # Example environment variables
├── .env                        # Environment variables (not in git)
├── pyproject.toml              # Project configuration and dependencies
├── setup.sh                    # Package setup script
├── langgraph.json              # LangGraph configuration
├── Dockerfile                  # Container definition
└── README.md                   # This file
```