FROM python:3.11-slim

ARG PYTHON_ENV=development
ENV PYTHON_ENV=$PYTHON_ENV

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD if [ "$PYTHON_ENV" = "production" ]; then \
        uvicorn src.api:app --host 0.0.0.0 --port 8000; \
    else \
        uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload --reload-dir src; \
    fi 