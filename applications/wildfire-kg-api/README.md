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

### LangGraph

The LangGraph server can be launched locally with the following command:
> [!NOTE]
> You must have the dev dependencies installed to launch a local LangGraph server.

```bash
# Start LangGraph Studio
langgraph dev
```

This will:
1. Start a local development server
2. Open LangSmith Studio in your browser
3. Allow you to visualize and debug your conversation graph
4. Provide access to your API endpoints

You can trace graph executions, inspect state at each node, and test your graph interactively.

### Evaluation

The LangGraph agent is currently evaluated using the LangSmith SDK and a variety of datasets defined in [evaluation/](data/evaluation/). 

The notebook [notebooks/langgraph/evaluate.ipynb](evaluation/evaluate.ipynb) provides an example of running an experiment that evaluates the agent's performance on the datasets. The experiment can be viewed in the LangSmith UI for detailed results. 
> [!NOTE]
> You must have the wildfire-kg-api package installed to run the evaluation notebook. Typically, running `source setup.sh dev` and `source setup.sh` should do the trick. 

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

At the moment, the LangGraph server is deployed using the LangGraph platform, but may be deployed with a custom container image in the future.

## Project Structure

```
wildfire-kg-api/
├── wildfire_kg_api/            # Main source code
│   ├── __init__.py             # Package initialization
│   ├── app.py                  # FastAPI application
│   ├── main.py                 # CLI and entry points
│   ├── routes/                 # API routes
│   │   ├── __init__.py         # Route registration system
│   │   ├── health.py           # Health check endpoints
│   │   └── s3.py               # S3 storage endpoints
│   └── orchestration/          # LangGraph orchestration
│       ├── prompts/            # Prompt templates
│       ├── tools/              # Tools for retrieving information
│       ├── agent.py            # ReAct tool calling agent definition
│       └── state.py            # Conversation state management and data models
├── .env.example                # Example environment variables
├── .env                        # Environment variables (not in git)
├── pyproject.toml              # Project configuration and dependencies
├── setup.sh                    # Package setup script
├── langgraph.json              # LangGraph configuration
├── Dockerfile                  # Container definition
└── README.md                   # This file
```
