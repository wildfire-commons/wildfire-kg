#!/usr/bin/env python
import streamlit as st
import json
import os
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import sys
import dotenv
from pathlib import Path

# Load environment variables from .env file if it exists
dotenv.load_dotenv()

# Add the project root to the Python path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))
from tests.utils.test_config_manager import TestConfigManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get default values from environment variables or use sensible defaults
DEFAULT_ASSISTANT_ID = os.getenv(
    "LANGGRAPH_ASSISTANT_ID", "62331b6a-310f-5cf9-b4ca-6e14ee929514"
)
DEFAULT_STUDIO_URL = os.getenv("LANGGRAPH_STUDIO_URL", "http://127.0.0.1:2024")
DEFAULT_STUDIO_UI_URL = os.getenv(
    "LANGGRAPH_STUDIO_UI_URL",
    "https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024",
)

# Create a manager instance
config_manager = TestConfigManager()

# Cache the assistant ID for the session
if "assistant_id" not in st.session_state:
    st.session_state.assistant_id = DEFAULT_ASSISTANT_ID
if "studio_url" not in st.session_state:
    st.session_state.studio_url = DEFAULT_STUDIO_URL
if "studio_ui_url" not in st.session_state:
    st.session_state.studio_ui_url = DEFAULT_STUDIO_UI_URL

# Set page config
st.set_page_config(
    page_title="LangGraph Test Config Manager",
    page_icon="🧪",
    layout="wide",
)


def main():
    """Main Streamlit app function."""
    st.title("LangGraph Test Config Manager")
    st.markdown(
        """
    This tool helps you manage test configurations for your LangGraph application.
    Save and load queries to avoid retyping them in the LangSmith UI.
    """
    )

    # App-wide settings in the sidebar
    st.sidebar.title("Settings")
    if st.sidebar.checkbox("Edit Global Settings", False):
        st.sidebar.markdown("### Global Settings")
        # Allow editing the global assistant ID
        new_assistant_id = st.sidebar.text_input(
            "Default Assistant ID",
            value=st.session_state.assistant_id,
            help="The default assistant ID to use for all configurations",
        )

        # Allow editing the global studio URL
        new_studio_url = st.sidebar.text_input(
            "Default Studio API URL",
            value=st.session_state.studio_url,
            help="The default LangGraph Studio API URL",
        )

        # Allow editing the global studio UI URL
        new_studio_ui_url = st.sidebar.text_input(
            "Default Studio UI URL",
            value=st.session_state.studio_ui_url,
            help="The default LangGraph Studio UI URL",
        )

        # Save button for global settings
        if st.sidebar.button("Save Global Settings"):
            st.session_state.assistant_id = new_assistant_id
            st.session_state.studio_url = new_studio_url
            st.session_state.studio_ui_url = new_studio_ui_url
            st.sidebar.success("Global settings saved!")

    # Display current assistant ID
    st.sidebar.markdown(f"**Current Assistant ID:** {st.session_state.assistant_id}")

    # Navigation in the sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Choose a page",
        [
            "Saved Configurations",
            "Create New Configuration",
            "Send to Studio",
            "LangGraph Server Status",
        ],
    )

    # Display page based on selection
    if page == "Saved Configurations":
        display_saved_configs()
    elif page == "Create New Configuration":
        create_new_config()
    elif page == "Send to Studio":
        send_to_studio()
    elif page == "LangGraph Server Status":
        check_server_status()


def check_server_status():
    """Check the status of the LangGraph server."""
    st.header("LangGraph Server Status")

    studio_url = st.text_input(
        "LangGraph Studio API URL",
        value=st.session_state.studio_url,
        help="The URL of the LangGraph Studio API",
    )

    if st.button("Check Server Status"):
        with st.spinner("Checking server status..."):
            try:
                if check_langgraph_server(studio_url):
                    # Get assistants
                    try:
                        assistants_response = requests.get(f"{studio_url}/assistants")
                        assistants_response.raise_for_status()
                        assistants = assistants_response.json()

                        st.subheader("Available Assistants")
                        for assistant in assistants:
                            with st.expander(
                                f"{assistant.get('name', 'Unnamed')} ({assistant.get('id', 'No ID')})"
                            ):
                                st.json(assistant)

                                # Add a button to set this as the current assistant
                                if st.button(
                                    f"Use this assistant",
                                    key=f"use_{assistant.get('id')}",
                                ):
                                    st.session_state.assistant_id = assistant.get("id")
                                    st.success(
                                        f"Set current assistant to: {assistant.get('id')}"
                                    )
                                    st.rerun()

                    except Exception as e:
                        st.warning(f"Could not fetch assistants: {e}")

            except Exception as e:
                st.error(f"❌ LangGraph server is not accessible: {e}")
                st.info(
                    "Make sure the LangGraph server is running with 'langgraph dev'"
                )


def check_langgraph_server(url):
    """Check if the LangGraph server is running."""
    try:
        # Use /assistants/search endpoint instead of /health for checking server availability
        response = requests.post(
            f"{url}/assistants/search", json={"limit": 1}, timeout=5
        )
        if response.status_code == 200:
            st.success(f"✅ LangGraph server is running at {url}")
            return True
        else:
            st.error(
                f"❌ LangGraph server returned status code {response.status_code} at {url}"
            )
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Could not connect to LangGraph server at {url}: {e}")
        return False


def display_saved_configs():
    """Display a list of saved configurations and allow viewing/editing."""
    st.header("Saved Test Configurations")

    configs = config_manager.list_configs()
    if not configs:
        st.info("No saved configurations found. Create a new one!")
        return

    # Select config to view
    selected_config = st.selectbox("Select a configuration to view", configs)

    if selected_config:
        config = config_manager.load_config(selected_config)

        # Display config details
        st.subheader(f"Configuration: {selected_config}")

        # Edit mode toggle
        edit_mode = st.checkbox("Edit Mode")

        if edit_mode:
            # Editable fields
            query = st.text_area("Query", value=config.get("query", ""), height=150)
            assistant_id = st.text_input(
                "Assistant ID",
                value=config.get("assistant_id", st.session_state.assistant_id),
            )
            studio_ui_url = st.text_input(
                "Studio UI URL",
                value=config.get("studio_ui_url", st.session_state.studio_ui_url),
            )

            # Additional parameters as JSON
            additional_params_str = st.text_area(
                "Additional Parameters (JSON)",
                value=json.dumps(
                    {
                        k: v
                        for k, v in config.items()
                        if k not in ["query", "assistant_id", "studio_ui_url"]
                    },
                    indent=2,
                ),
                height=150,
            )

            # Save button
            if st.button("Save Changes"):
                try:
                    additional_params = json.loads(additional_params_str)
                    updated_config = {
                        "query": query,
                        "assistant_id": assistant_id,
                        "studio_ui_url": studio_ui_url,
                        **additional_params,
                    }
                    config_manager.save_config(selected_config, updated_config)
                    st.success(
                        f"Configuration '{selected_config}' updated successfully!"
                    )
                except json.JSONDecodeError:
                    st.error("Failed to parse additional parameters as JSON")

            # Delete button
            if st.button(
                "Delete Configuration",
                type="primary",
                help="This action cannot be undone",
            ):
                file_path = config_manager.config_dir / f"{selected_config}.json"
                try:
                    os.remove(file_path)
                    st.success(
                        f"Configuration '{selected_config}' deleted successfully!"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to delete configuration: {e}")
        else:
            # View-only mode
            st.markdown("### Query")
            st.code(config.get("query", ""), language="text")

            st.markdown("### Details")
            st.json(config)

            # Quick send button
            if st.button("Send this query to Studio"):
                with st.spinner("Sending query to LangGraph Studio..."):
                    try:
                        thread_url = config_manager.send_to_studio(
                            selected_config, st.session_state.studio_url
                        )
                        st.success(
                            f"Query from configuration '{selected_config}' sent to LangGraph Studio"
                        )

                        if thread_url:
                            st.markdown(
                                f"[Click here to view the conversation]({thread_url})"
                            )
                        else:
                            st.warning(
                                "Could not get a valid thread URL. Check the logs for details."
                            )

                    except Exception as e:
                        st.error(f"Failed to send query: {str(e)}")
                        st.info(
                            "Check the server logs for details and make sure the LangGraph server is running."
                        )


def create_new_config():
    """Create a new test configuration."""
    st.header("Create New Test Configuration")

    # Configuration name
    name = st.text_input(
        "Configuration Name", help="A unique name for this configuration"
    )

    # Query
    query = st.text_area(
        "Query", height=150, help="The query to send to your LangGraph application"
    )

    # Assistant ID (use the current session's assistant ID as default)
    assistant_id = st.text_input(
        "Assistant ID",
        value=st.session_state.assistant_id,
        help="The ID of the assistant to use",
    )

    # Studio UI URL (use the current session's studio UI URL as default)
    studio_ui_url = st.text_input(
        "Studio UI URL",
        value=st.session_state.studio_ui_url,
        help="The URL to access the LangGraph Studio UI",
    )

    # Additional parameters
    additional_params_str = st.text_area(
        "Additional Parameters (JSON, optional)",
        value="{}",
        height=100,
        help="Any additional parameters to include in the configuration as JSON",
    )

    # Save button
    if st.button("Save Configuration"):
        if not name:
            st.error("Configuration name is required")
            return

        if not query:
            st.error("Query is required")
            return

        if not assistant_id:
            st.warning(
                "Assistant ID is missing. The configuration may not work without it."
            )

        try:
            additional_params = json.loads(additional_params_str)
            config = {
                "query": query,
                "assistant_id": assistant_id,
                "studio_ui_url": studio_ui_url,
                **additional_params,
            }
            config_manager.save_config(name, config)
            st.success(f"Configuration '{name}' saved successfully!")

            # Clear form
            st.rerun()
        except json.JSONDecodeError:
            st.error("Failed to parse additional parameters as JSON")


def send_to_studio():
    """Send a configuration to LangGraph Studio."""
    if not st.session_state.selected_config:
        st.warning("Please select a configuration first")
        return

    with st.container():
        st.write("##### Send Configuration to LangGraph Studio")
        studio_url = st.text_input(
            "LangGraph Studio URL",
            value=st.session_state.studio_url,
            key="send_studio_url",
        )

        # Create columns for assistant ID and send button
        col1, col2 = st.columns([3, 1])

        # Show current assistant ID and allow user to change it
        with col1:
            config = config_manager.load_config(st.session_state.selected_config)
            current_assistant_id = config.get("assistant_id", "")

            if not current_assistant_id:
                current_assistant_id = st.session_state.assistant_id
                st.warning(
                    "⚠️ No assistant ID in this config - using default from settings"
                )

            new_assistant_id = st.text_input(
                "Assistant ID for this query",
                value=current_assistant_id,
                key="send_assistant_id",
            )

            # If the assistant ID changed, update the config
            if new_assistant_id != current_assistant_id:
                config["assistant_id"] = new_assistant_id
                config_manager.save_config(st.session_state.selected_config, config)
                st.success(
                    f"Updated assistant ID for {st.session_state.selected_config}"
                )

        with col2:
            send_button = st.button("Send to Studio", key="send_button")

        if send_button:
            with st.spinner("Creating LangGraph run from configuration..."):
                # Check if assistant ID is provided
                config = config_manager.load_config(st.session_state.selected_config)
                if not config.get("assistant_id"):
                    st.error(
                        "⚠️ No assistant ID provided. Please add an assistant ID to the configuration."
                    )
                    return

                # Send to studio and create run
                thread_url = config_manager.send_to_studio(
                    st.session_state.selected_config, studio_url
                )
                if thread_url:
                    st.success("Run created successfully!")
                    st.markdown(
                        f"[Click here to view the conversation and run]({thread_url})"
                    )
                else:
                    st.error("Failed to create run. See logs for details.")


if __name__ == "__main__":
    main()
