"""
Main entry point for the Wildfire Knowledge Graph API.

This module provides:
1. CLI commands to run the FastAPI server directly (without LangGraph Studio)

Usage:
    # Run the API server directly
    python -m src.main run
    
    # Run in development mode with auto-reload
    python -m src.main run --dev
"""

import logging
import click
import uvicorn
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version="0.1.0", prog_name="Wildfire KG API")
def cli():
    """
    Wildfire Knowledge Graph API CLI.

    This CLI provides commands to run and manage the Wildfire KG API.
    """
    pass


@cli.command(name="run", help="Run the API server directly (without LangGraph Studio)")
@click.option(
    "--dev", "-d", is_flag=True, help="Run in development mode with auto-reload"
)
@click.option("--host", "-h", default="0.0.0.0", help="Host to run the server on")
@click.option("--port", "-p", default=8000, help="Port to run the server on")
def run_server(dev, host, port):
    """Run the API server directly without LangGraph Studio."""
    # Common import path - but importing the string rather than module
    uvicorn_app_path = "src.app:app"

    if dev:
        logger.info(f"Starting API server in development mode on {host}:{port}...")
        # Use a more restrictive reload pattern to avoid excessive reloads
        uvicorn.run(
            uvicorn_app_path,
            host=host,
            port=port,
            reload=True,
            reload_dirs=["src"],
            reload_excludes=["__pycache__", "*.pyc", "*.pyo"],
        )
    else:
        logger.info(f"Starting API server on {host}:{port}...")
        # In production mode, directly import the app
        from src.app import app

        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli()
