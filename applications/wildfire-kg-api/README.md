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

# For all dependencies
./setup.sh all
```

3. Configure your environment variables in the `.env` file:

```
OPENAI_API_KEY=your_openai_key
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
TAVILY_API_KEY=your_tavily_key  # Optional, for web search
```

4. (Optional) For easier CLI access, install the package in development mode:

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Install with production dependencies
pip install -e ".[prod]"

# Install with all dependencies
pip install -e ".[all]"
```

This will make the `wkg` command available globally.

### Shell Completion

For even easier CLI usage, you can set up shell completion:

```bash
# For Bash
wkg completion bash >> ~/.bash_completion

# For Zsh
wkg completion zsh > ~/.zsh_completion/_wkg

# For Fish
wkg completion fish > ~/.config/fish/completions/wkg.fish
```

## Dependency Management

The project uses separate requirement files for different environments:

- `requirements/base.txt`: Core dependencies needed for all environments
- `requirements/dev.txt`: Development dependencies (testing, linting, documentation)
- `requirements/prod.txt`: Production dependencies

You can install these dependencies using pip:

```bash
# Install base dependencies
pip install -r requirements/base.txt

# Install development dependencies
pip install -r requirements/dev.txt

# Install production dependencies
pip install -r requirements/prod.txt
```

Or using the setup.py extras:

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Install with production dependencies
pip install -e ".[prod]"

# Install with all dependencies
pip install -e ".[all]"
```

## Running the API

You can run the API in different ways:

### Using the run.sh script

```bash
# Standard mode
./run.sh

# Development mode
./run.sh dev

# LangGraph Studio
./run.sh studio

# Help
./run.sh help
```

### Using the Python module

```bash
# Standard mode
python -m src.main run

# Development mode (shortcut)
python -m src.main dev

# Development mode (alternative)
python -m src.main run --dev

# LangGraph Studio
python -m src.main studio
```

### Using the wkg command (if installed with pip)

```bash
# Standard mode
wkg run

# Development mode
wkg dev

# LangGraph Studio
wkg studio

# Show help
wkg --help
```

### Command-line Options

```bash
# Get help on available commands
wkg --help

# Get help on a specific command
wkg run --help
```

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
│   ├── main.py                 # CLI entry point
│   ├── routes/
│   │   ├── chat_routes.py      # Chat endpoints
│   │   └── s3.py               # S3 endpoints
│   ├── orchestration/
│   │   ├── graph/              # LangGraph definitions
│   │   ├── agents/             # Agent definitions
│   │   ├── tools/              # Tool integrations
│   │   └── state/              # State definitions
│   └── ...
├── requirements/
│   ├── base.txt                # Core dependencies
│   ├── dev.txt                 # Development dependencies
│   └── prod.txt                # Production dependencies
├── requirements.txt            # Points to requirements/prod.txt
├── setup.py                    # Package setup for pip installation
├── setup.sh                    # Environment setup script
├── run.sh                      # Convenience script for running the API
└── ...
```

## Development

### Adding New Tools

To add a new tool:

1. Create a new tool in `src/orchestration/tools/`
2. Update the graph in `src/orchestration/graph/chat_graph.py`
3. Update the router agent in `src/orchestration/agents/router_agent.py`

### Testing

You can test the LangGraph workflow using LangGraph Studio:

```bash
./run.sh studio
# or
wkg studio
```

This will start a local server where you can visualize and debug your graph.

## License

[Your License] 