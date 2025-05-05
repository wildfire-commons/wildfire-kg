FROM python:3.11-slim

ARG PYTHON_ENV=development
ENV PYTHON_ENV=$PYTHON_ENV

WORKDIR /app

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire project first
COPY . .

# Install dependencies - for dev, we install both prod dependencies + dev extras
RUN pip install --no-cache-dir --upgrade pip && \
    if [ "$PYTHON_ENV" = "production" ]; then \
        echo "Installing production dependencies" && \
        pip install --no-cache-dir .; \
    else \
        echo "Installing development dependencies (includes production)" && \
        pip install --no-cache-dir ".[dev]"; \
    fi

CMD if [ "$PYTHON_ENV" = "production" ]; then \
        uvicorn wildfire_kg_api.app:app --host 0.0.0.0 --port 8000; \
    else \
        uvicorn wildfire_kg_api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir wildfire_kg_api; \
    fi 