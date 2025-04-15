"""
Main entry point for the Wildfire Knowledge Graph API.

This module provides:
1. CLI commands to run the FastAPI server directly (without LangGraph Studio)

Usage:
    # Run the API server directly
    wkg-api run

    # Run in development mode
    wkg-api run --dev
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
    uvicorn_app_path = "wildfire_kg_api.app:app"

    if dev:
        logger.info(f"Starting API server in development mode on {host}:{port}...")
        # Use a more restrictive reload pattern to avoid excessive reloads
        uvicorn.run(
            uvicorn_app_path,
            host=host,
            port=port,
            reload=True,
            reload_dirs=["wildfire_kg_api"],
            reload_excludes=["__pycache__", "*.pyc", "*.pyo"],
        )
    else:
        logger.info(f"Starting API server on {host}:{port}...")
        # In production mode, directly import the app
        from wildfire_kg_api.app import app

        uvicorn.run(app, host=host, port=port)


@cli.command(name="ui", help="Launch the Streamlit UI for testing and development")
@click.option("--port", "-p", default=8501, help="Port to run Streamlit on")
def launch_streamlit(port):
    """Launch the Streamlit UI for testing and development."""
    try:
        import streamlit.web.cli as stcli
        import sys
        from pathlib import Path

        # Find the streamlit app file in the streamlit directory
        streamlit_dir = Path(__file__).parent.parent / "tests" / "streamlit"
        app_path = streamlit_dir / "app.py"

        if not app_path.exists():
            click.echo(
                click.style(f"Error: Streamlit app not found at {app_path}", fg="red")
            )
            click.echo(
                "Make sure you have installed the dev dependencies with 'pip install -e \".[dev]\"'"
            )
            return

        # Prepare arguments for streamlit
        sys.argv = [
            "streamlit",
            "run",
            str(app_path),
            "--server.port",
            str(port),
            "--browser.serverAddress",
            "localhost",
        ]

        click.echo(
            click.style(f"Starting Streamlit UI on http://localhost:{port}", fg="green")
        )
        click.echo("Press Ctrl+C to stop")

        # Run streamlit
        stcli.main()
    except ImportError:
        click.echo(click.style("Error: Streamlit is not installed", fg="red"))
        click.echo("Install development dependencies with: pip install -e '.[dev]'")


if __name__ == "__main__":
    cli()
