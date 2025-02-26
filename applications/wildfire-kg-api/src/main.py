"""
Main entry point for the Wildfire Knowledge Graph API.

This module provides different ways to run the application:
- Standard API server
- Development mode with auto-reload
- LangGraph Studio for visualizing and debugging the conversation graph

Usage:
    # Run the standard API server
    python -m src.main run
    
    # Run in development mode with auto-reload
    python -m src.main run --dev
    
    # Run LangGraph Studio
    python -m src.main studio
"""

import os
import sys
import logging
import importlib.util
import click
import uvicorn
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def check_dependency(package_name):
    """Check if a dependency is installed."""
    return importlib.util.find_spec(package_name) is not None


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version="0.1.0", prog_name="Wildfire KG API")
def cli():
    """Wildfire Knowledge Graph API CLI.

    This CLI provides commands for running the API server and LangGraph Studio.
    """
    pass


@cli.command(name="run", help="Run the API server")
@click.option(
    "--dev", "-d", is_flag=True, help="Run in development mode with auto-reload"
)
@click.option("--host", "-h", default="0.0.0.0", help="Host to run the server on")
@click.option("--port", "-p", default=8000, help="Port to run the server on")
def run_server(dev, host, port):
    """Run the API server."""
    if dev:
        logger.info(f"Starting API server in development mode on {host}:{port}...")
        uvicorn.run("src.app:app", host=host, port=port, reload=True)
    else:
        logger.info(f"Starting API server on {host}:{port}...")
        # Import here to avoid circular imports
        from .app import app

        uvicorn.run(app, host=host, port=port)


@cli.command(name="studio", help="Run the LangGraph Studio server")
@click.option("--port", "-p", default=8000, help="Port to run the server on")
def run_studio(port):
    """Run the LangGraph Studio server."""
    # Check for required dependencies
    missing_deps = []
    for dep in ["langchain_cli", "langserve"]:
        if not check_dependency(dep):
            missing_deps.append(dep)

    if missing_deps:
        logger.error(
            f"Missing dependencies for LangGraph Studio: {', '.join(missing_deps)}"
        )
        logger.error("Install development dependencies with: pip install -e '.[dev]'")
        sys.exit(1)

    try:
        from langchain_cli.langchain_cli import serve_langchain_studio
        from langserve import add_routes
        from fastapi import FastAPI
        from .orchestration.graph.chat_graph import (
            create_chat_graph,
            process_user_message,
        )

        # Check if the required environment variables are set
        if not os.getenv("OPENAI_API_KEY"):
            logger.error("OPENAI_API_KEY environment variable is not set")
            sys.exit(1)

        # Create the graph
        graph = create_chat_graph()

        # Create a FastAPI app for LangGraph Studio
        studio_app = FastAPI(
            title="Wildfire Knowledge Graph Chatbot",
            version="0.1.0",
            description="A chatbot that can answer questions about wildfires using a knowledge graph and RAG.",
        )

        # Add routes for the graph
        add_routes(
            studio_app,
            graph,
            path="/api/chat-graph",
        )

        # Add a route for the process_user_message function
        add_routes(
            studio_app,
            process_user_message,
            path="/api/chat",
        )

        logger.info(f"Starting LangGraph Studio server on port {port}...")
        serve_langchain_studio(studio_app, port=port)
    except Exception as e:
        logger.error(f"Error starting LangGraph Studio: {str(e)}")
        sys.exit(1)


@cli.command(name="dev", help="Shortcut to run in development mode")
@click.option("--host", "-h", default="0.0.0.0", help="Host to run the server on")
@click.option("--port", "-p", default=8000, help="Port to run the server on")
def run_dev(host, port):
    """Shortcut to run the API server in development mode."""
    run_server(dev=True, host=host, port=port)


@cli.command(name="completion", help="Generate shell completion script")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def generate_completion(shell):
    """Generate shell completion script for the CLI."""
    completion_script = ""

    if shell == "bash":
        completion_script = """
# Bash completion script for wkg
_wkg_completion() {
    local IFS=$'\n'
    local response

    response=$(env COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD=$COMP_CWORD _WKG_COMPLETE=bash_complete $1)

    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        if [[ $type == 'dir' ]]; then
            COMPREPLY=( $(compgen -d -- "$value") )
        elif [[ $type == 'file' ]]; then
            COMPREPLY=( $(compgen -f -- "$value") )
        elif [[ $type == 'plain' ]]; then
            COMPREPLY+=($value)
        fi
    done
    return 0
}

complete -F _wkg_completion -o nospace wkg
"""
    elif shell == "zsh":
        completion_script = """
# Zsh completion script for wkg
_wkg_completion() {
    local -a completions
    local -a completions_with_descriptions
    local -a response
    response=("${(@f)$(env COMP_WORDS="${words[*]}" COMP_CWORD=$((CURRENT-1)) _WKG_COMPLETE=zsh_complete wkg)}")

    for key value in ${(kv)response}; do
        if [[ "$value" == "_" ]]; then
            completions+=("$key")
        else
            completions_with_descriptions+=("$key:$value")
        fi
    done

    if [ ${#completions_with_descriptions} -gt 0 ]; then
        _describe -V unsorted completions_with_descriptions -U
    fi

    if [ ${#completions} -gt 0 ]; then
        compadd -U -V unsorted -a completions
    fi
    compstate[insert]=menu
}

compdef _wkg_completion wkg
"""
    elif shell == "fish":
        completion_script = """
# Fish completion script for wkg
function __fish_wkg_complete
    set -l response (env _WKG_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) wkg)
    for completion in $response
        set -l metadata (string split "," $completion)
        if test $metadata[1] = "dir"
            __fish_complete_directories $metadata[2]
        else if test $metadata[1] = "file"
            __fish_complete_path $metadata[2]
        else if test $metadata[1] = "plain"
            echo $metadata[2]
        end
    end
end

complete -c wkg -f -a "(__fish_wkg_complete)"
"""

    click.echo(completion_script)
    click.echo(
        f"\n# Add this to your ~/.{shell}rc file or save it to ~/.{shell}_completion/wkg"
    )
    click.echo(
        f"# You can also run: wkg completion {shell} >> ~/.{shell}_completion/wkg"
    )


if __name__ == "__main__":
    cli()
