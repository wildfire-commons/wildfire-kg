FROM python:3.11-slim

ARG PYTHON_ENV=development
ENV PYTHON_ENV=$PYTHON_ENV

WORKDIR /app

# Copy pyproject.toml and other necessary files for installation
COPY pyproject.toml ./

# Install dependencies - for dev, we install both prod dependencies + dev extras
RUN pip install --no-cache-dir --upgrade pip && \
    if [ "$PYTHON_ENV" = "production" ]; then \
        echo "Installing production dependencies" && \
        pip install --no-cache-dir .; \
    else \
        echo "Installing development dependencies (includes production)" && \
        pip install --no-cache-dir ".[dev]"; \
    fi

# Copy the rest of the application
COPY . .

CMD if [ "$PYTHON_ENV" = "production" ]; then \
        uvicorn src.api:app --host 0.0.0.0 --port 8000; \
    else \
        uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload --reload-dir src; \
    fi 