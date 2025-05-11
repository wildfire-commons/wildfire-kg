FROM python:3.11-slim

ARG PYTHON_ENV=development
ENV PYTHON_ENV=$PYTHON_ENV

WORKDIR /app

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire project first
COPY . .

# Install dependencies - for dev, we install both prod dependencies + dev extras
RUN pip install --no-cache-dir --upgrade pip && \
    if [ "$PYTHON_ENV" = "production" ]; then \
        echo "Installing production dependencies" && \
        pip install --no-cache-dir . && \
        pip install --no-cache-dir "langgraph>=0.3.27" langchain-openai>=0.3.7 langchain-core>=0.3.40 uvicorn[standard]; \
    else \
        echo "Installing development dependencies (includes production)" && \
        pip install --no-cache-dir ".[dev]" && \
        pip install --no-cache-dir "langgraph>=0.3.27" langchain-openai>=0.3.7 langchain-core>=0.3.40 uvicorn[standard]; \
    fi

# Set environment variables for LangGraph
ENV LANGGRAPH_HTTP='{"app": "src.app:app"}'
ENV PYTHONPATH=/app

# Expose the port
EXPOSE 8000

# Run the application
CMD if [ "$PYTHON_ENV" = "production" ]; then \
        uvicorn src.app:app --host 0.0.0.0 --port 8000; \
    else \
        uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir src; \
    fi 