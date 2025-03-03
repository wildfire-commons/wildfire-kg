# Wildfire Knowledge Graph API

This API provides access to the wildfire knowledge graph and includes a conversational AI interface powered by LangGraph.

## Features

- Knowledge graph querying with natural language
- Conversational AI interface using LangGraph
- Integration with external data sources through RAG
- LangGraph Studio support for visualization and debugging

## Setup

### Prerequisites

- Python 3.9+
- Neo4j database (for knowledge graph)
- OpenAI API key
- Tavily API key (optional, for web search)

### Installation

1. Clone the repository
2. Run the setup script with the desired environment:

```bash
cd wildfire-kg-api

# For development environment (includes testing and debugging tools)
./setup.sh dev

# For production environment (minimal dependencies)
./setup.sh prod
```

3. Configure your environment variables:

The setup script creates environment-specific .env files (.env.dev for development, .env.prod for production) and links the appropriate one to .env based on your chosen environment. You should update the variables in these files:

```
# Common variables for both environments
OPENAI_API_KEY=your_openai_key
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
TAVILY_API_KEY=your_tavily_key  # Optional, for web search

# Development-specific variables (.env.dev)
DEBUG=True
LOG_LEVEL=DEBUG

# Production-specific variables (.env.prod)
DEBUG=False
LOG_LEVEL=INFO
```

## Running the API

If not already activated, activate the virtual environment:
```bash
source venv/bin/activate
```

### Standard API Server

```bash
# Start the API server with auto-reload
uvicorn src.app:app --reload
```

### LangGraph Studio

With the updated LangGraph integration, you can use the LangGraph CLI for development:

```bash
# Make sure you're in the API directory
cd applications/wildfire-kg-api

# Start LangGraph Studio
langgraph dev
```

This will:
1. Start a local development server
2. Open LangGraph Studio in your browser
3. Allow you to visualize and debug your conversation graph
4. Provide access to your API endpoints

You can trace graph executions, inspect state at each node, and test your graph interactively.

## API Endpoints

### Chat Endpoint

```
POST /api/chat
```

Request body:
```json
{
  "message": "What's the average canopy height in the San Bernardino forest?",
  "history": [
    {
      "id": "msg-1",
      "text": "Hello, I have a question about forest data.",
      "sender": "user",
      "timestamp": "2023-04-01T12:00:00Z"
    },
    {
      "id": "msg-2",
      "text": "I'd be happy to help with forest data. What would you like to know?",
      "sender": "assistant",
      "timestamp": "2023-04-01T12:00:05Z"
    }
  ]
}
```

Response:
```json
{
  "message": {
    "id": "response-1234567890",
    "text": "Based on our knowledge graph, the average canopy height in the San Bernardino forest is approximately 25 meters.",
    "sender": "assistant",
    "timestamp": "2023-04-01T12:00:10Z"
  },
  "context": {
    "kg_results": { ... },
    "rag_results": { ... },
    "routing": { ... }
  }
}
```

## Architecture

The API uses a LangGraph orchestration layer to handle conversations:

1. **Router Agent**: Decides which tools to use based on the query
2. **Knowledge Graph Tool**: Queries the Neo4j knowledge graph
3. **RAG Tool**: Retrieves information from external sources
4. **Response Generator**: Creates the final response

The LangGraph workflow is defined in `src/orchestration/graph/chat_graph.py`.

## Project Structure

```
wildfire-kg-api/
├── src/
│   ├── app.py                  # FastAPI application
│   ├── main.py                 # Core functionality and graph access
│   ├── routes/
│   │   ├── chat_routes.py      # Chat endpoints
│   │   └── s3.py               # S3 endpoints
│   ├── orchestration/
│   │   ├── graph/              # LangGraph definitions
│   │   ├── agents/             # Agent definitions
│   │   ├── tools/              # Tool integrations
│   │   └── state/              # State definitions
│   └── ...
├── pyproject.toml              # Project dependencies and configuration
├── langgraph.json              # LangGraph configuration
├── .env.dev                    # Development environment variables
├── .env.prod                   # Production environment variables
├── .env                        # Symlink to active environment file
├── setup.sh                    # Environment setup script
└── ...
```