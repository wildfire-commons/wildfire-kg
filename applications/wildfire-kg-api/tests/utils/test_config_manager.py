#!/usr/bin/env python
import json
import argparse
import requests
import urllib.parse
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default configuration directory
CONFIG_DIR = Path("./tests/test_configs")


class TestConfigManager:
    """
    Utility for managing test configurations for LangGraph Studio.
    Allows saving and loading test queries and configurations.
    """

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize the TestConfigManager with a configuration directory."""
        self.config_dir = Path(config_dir or CONFIG_DIR)
        self.config_dir.mkdir(exist_ok=True, parents=True)
        logger.info(f"Using configuration directory: {self.config_dir.absolute()}")

    def save_config(self, name: str, config: Dict[str, Any]) -> None:
        """Save a configuration to a JSON file."""
        file_path = self.config_dir / f"{name}.json"
        with open(file_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved configuration '{name}' to {file_path}")

    def load_config(self, name: str) -> Dict[str, Any]:
        """Load a configuration from a JSON file."""
        file_path = self.config_dir / f"{name}.json"
        if not file_path.exists():
            logger.error(f"Configuration '{name}' not found at {file_path}")
            return {}

        with open(file_path, "r") as f:
            config = json.load(f)
        logger.info(f"Loaded configuration '{name}' from {file_path}")
        return config

    def list_configs(self) -> List[str]:
        """List all available configurations."""
        configs = [f.stem for f in self.config_dir.glob("*.json")]
        return configs

    def send_to_studio(
        self, name: str, studio_url: str = "http://127.0.0.1:2024"
    ) -> None:
        """
        Send a saved configuration to the LangGraph Studio UI.
        This will create a new thread and send the configuration as a message.

        Args:
            name: Name of the configuration to send
            studio_url: URL of the LangGraph Studio API server
        """
        try:
            config = self.load_config(name)
            logger.info(
                f"Sending query from '{name}' to assistant '{config.get('assistant_id')}' at {studio_url}"
            )

            # Validate URL format
            if not studio_url.startswith(("http://", "https://")):
                logger.error(
                    f"Invalid studio URL format: {studio_url}. Must start with http:// or https://"
                )
                return

            # Check if LangGraph Studio API is accessible
            try:
                # Use /assistants/search endpoint instead of /health for checking server availability
                health_response = requests.post(
                    f"{studio_url}/assistants/search", json={"limit": 1}, timeout=5
                )
                if health_response.status_code != 200:
                    logger.error(
                        f"LangGraph Studio API returned unexpected status: {health_response.status_code} for url: {studio_url}/assistants/search"
                    )
                    logger.error(
                        "Make sure the LangGraph server is running (langgraph dev)"
                    )
                    return
            except requests.exceptions.RequestException as e:
                logger.error(
                    f"LangGraph Studio API is not accessible at {studio_url}: {e}"
                )
                logger.error(
                    "Make sure the LangGraph server is running (langgraph dev)"
                )
                return

            # Check if the assistant_id is provided and valid
            assistant_id = config.get("assistant_id")
            if not assistant_id:
                logger.error(
                    "No assistant_id provided in the configuration. Cannot send to LangGraph Studio."
                )
                return

            # Verify assistant exists
            try:
                # Try getting assistant info instead of schemas, which is more reliable
                assistant_url = f"{studio_url}/assistants/{assistant_id}"
                logger.info(f"Checking if assistant exists at: {assistant_url}")
                assistant_response = requests.get(assistant_url, timeout=5)

                # Log the response status
                logger.info(
                    f"Assistant check response status: {assistant_response.status_code}"
                )

                if assistant_response.status_code != 200:
                    logger.error(
                        f"Assistant with ID '{assistant_id}' not found. Status: {assistant_response.status_code}"
                    )
                    try:
                        # Try to parse the error message
                        error_content = assistant_response.json()
                        logger.error(f"Error details: {error_content}")
                    except:
                        logger.error(f"Raw response: {assistant_response.text}")
                    return

                # Log successful assistant check
                logger.info(f"Successfully verified assistant '{assistant_id}' exists")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error checking assistant with ID '{assistant_id}': {e}")
                return

            # Create a new thread
            try:
                thread_response = requests.post(
                    f"{studio_url}/threads",
                    json={"assistant_id": assistant_id},
                    timeout=5,
                )
                thread_response.raise_for_status()
                thread_data = thread_response.json()

                # Debug log the response
                logger.info(f"Thread creation response: {thread_data}")

                # Check if response has expected structure
                if not thread_data:
                    logger.error("Thread response is empty")
                    return

                # Extract thread ID - handle different possible response structures
                thread_id = None
                if isinstance(thread_data, dict):
                    # Try different possible key names
                    thread_id = thread_data.get("id") or thread_data.get("thread_id")

                    # If we still don't have a thread_id, log the full response structure to help debug
                    if not thread_id:
                        logger.error(
                            f"Could not find thread ID in response. Available keys: {list(thread_data.keys())}"
                        )
                        if "data" in thread_data and isinstance(
                            thread_data["data"], dict
                        ):
                            logger.info("Found 'data' key, checking for ID inside it")
                            thread_id = thread_data["data"].get("id") or thread_data[
                                "data"
                            ].get("thread_id")
                else:
                    logger.error(f"Unexpected response type: {type(thread_data)}")

                if not thread_id:
                    logger.error("Failed to create thread: No thread ID returned")
                    logger.error(f"Full response: {thread_data}")
                    return

                logger.info(f"Created thread with ID: {thread_id}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error creating thread: {e}")
                if hasattr(e, "response") and e.response is not None:
                    logger.error(f"Response status code: {e.response.status_code}")
                    logger.error(f"Response content: {e.response.content}")
                return

            # Send the message with the configuration
            try:
                # Instead of sending a message, create a run with the input
                logger.info(
                    f"Creating run on thread {thread_id} with assistant {assistant_id}"
                )

                run_request = {
                    "assistant_id": assistant_id,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": config.get("query", ""),
                            }
                        ],
                        "metadata": {"config_name": name, "test_config": True},
                    },
                }

                logger.info(f"Run request: {run_request}")

                run_response = requests.post(
                    f"{studio_url}/threads/{thread_id}/runs",
                    json=run_request,
                    timeout=10,
                )

                logger.info(f"Run creation response status: {run_response.status_code}")

                if run_response.status_code != 200:
                    logger.error(
                        f"Failed to create run: Server returned status {run_response.status_code}"
                    )
                    logger.error(f"Response content: {run_response.text}")
                    return

                try:
                    run_data = run_response.json()
                    logger.info(f"Run creation response: {run_data}")
                    run_id = run_data.get("id") or run_data.get("run_id")

                    if not run_id:
                        logger.error("Could not extract run ID from response")
                    else:
                        logger.info(f"Created run with ID: {run_id}")
                except Exception as e:
                    logger.error(f"Failed to parse run response: {e}")

                # Create the direct URL to view in LangSmith UI
                encoded_url = urllib.parse.quote(studio_url)
                thread_url = f"https://smith.langchain.com/studio/thread/{thread_id}?baseUrl={encoded_url}"

                logger.info(f"Run created on thread {thread_id}")
                logger.info(f"Click here to view the conversation: {thread_url}")
                return thread_url
            except requests.exceptions.RequestException as e:
                logger.error(f"Error creating run for thread {thread_id}: {e}")
                if hasattr(e, "response") and e.response is not None:
                    logger.error(f"Response status code: {e.response.status_code}")
                    logger.error(f"Response content: {e.response.content}")
                return
        except Exception as e:
            logger.error(f"Error sending configuration to LangGraph Studio: {e}")
            return


def main():
    """CLI entrypoint for the TestConfigManager."""
    parser = argparse.ArgumentParser(
        description="Manage test configurations for LangGraph Studio"
    )
    parser.add_argument(
        "--config-dir", help="Directory to store configurations", default=None
    )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Save command
    save_parser = subparsers.add_parser("save", help="Save a test configuration")
    save_parser.add_argument("name", help="Name of the configuration")
    save_parser.add_argument("--query", help="Query string to save", required=True)
    save_parser.add_argument("--assistant-id", help="Assistant ID", default="")
    save_parser.add_argument(
        "--additional-params", help="Additional parameters as JSON", default="{}"
    )

    # Load command
    load_parser = subparsers.add_parser("load", help="Load a test configuration")
    load_parser.add_argument("name", help="Name of the configuration to load")

    # List command
    list_parser = subparsers.add_parser("list", help="List all test configurations")

    # Send command
    send_parser = subparsers.add_parser(
        "send", help="Send a test configuration to LangGraph Studio"
    )
    send_parser.add_argument("name", help="Name of the configuration to send")
    send_parser.add_argument(
        "--studio-url",
        help="URL of LangGraph Studio API",
        default="http://127.0.0.1:2024",
    )

    args = parser.parse_args()
    manager = TestConfigManager(args.config_dir)

    if args.command == "save":
        # Parse additional parameters
        try:
            additional_params = json.loads(args.additional_params)
        except json.JSONDecodeError:
            logger.error("Failed to parse additional parameters as JSON")
            additional_params = {}

        # Create the configuration
        config = {
            "query": args.query,
            "assistant_id": args.assistant_id,
            "studio_ui_url": "https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024",
            **additional_params,
        }

        manager.save_config(args.name, config)

    elif args.command == "load":
        config = manager.load_config(args.name)
        print(json.dumps(config, indent=2))

    elif args.command == "list":
        configs = manager.list_configs()
        if configs:
            print("Available configurations:")
            for config in configs:
                print(f"- {config}")
        else:
            print("No configurations found")

    elif args.command == "send":
        try:
            url = manager.send_to_studio(args.name, args.studio_url)
            print(f"Access the conversation at: {url}")
        except Exception as e:
            logger.error(f"Error: {e}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
