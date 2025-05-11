"""
Prompt registry - a central place for accessing prompts.
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging
import yaml

from langchain.prompts import ChatPromptTemplate, PromptTemplate

logger = logging.getLogger(__name__)


class PromptRegistry:
    """
    A singleton registry that loads and provides access to prompts from YAML files.

    Automatically creates namespaced prompt names like:
    - agents.agent_prompt (for prompts in agents/ directory)
    - tools.kg.sparql_generation_prompt (for prompts in tools/ directory)
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptRegistry, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the registry by loading prompts from files."""
        self._prompts: Dict[str, PromptTemplate] = {}
        self._prompts_dir = Path(__file__).parent
        self.refresh()

    def _create_prompt_from_yaml(self, file_path: str) -> PromptTemplate:
        """Create a prompt template from a YAML file."""
        try:
            # Load YAML
            with open(file_path, "r") as file:
                yaml_data = yaml.safe_load(file)

            template_data = yaml_data.get("template", {})
            template_type = template_data.get("type")

            # Create appropriate prompt type
            if template_type == "chat":
                messages = template_data.get("messages", [])
                return ChatPromptTemplate.from_messages(
                    [(msg["role"], msg["content"]) for msg in messages]
                )
            elif template_type == "text":
                template_str = template_data.get("template", "")
                return PromptTemplate.from_template(template_str)
            else:
                raise ValueError(f"Unsupported template type: {template_type}")
        except Exception as e:
            logger.error(f"Error creating prompt from {file_path}: {e}")
            return None

    def refresh(self):
        """Reload all prompts from files."""
        self._prompts = {}
        prompt_dir = self._prompts_dir

        # Find all YAML files in the prompts directory and subdirectories
        for file_path in prompt_dir.glob("**/*.yaml"):
            try:
                # Skip hidden files and directories
                if any(part.startswith(".") for part in file_path.parts):
                    continue

                # Get the relative path from prompts directory
                rel_path = file_path.relative_to(prompt_dir)
                parts = list(rel_path.parts)

                # Skip the file itself to get directory structure
                parts = parts[:-1]
                # Add the filename without extension
                parts.append(file_path.stem)

                # Create the appropriate prompt name
                if len(parts) > 1:
                    # For nested paths like tools/kg/prompt.yaml, create tools.kg.prompt
                    prompt_name = ".".join(parts)
                else:
                    # For files in the root prompts directory
                    prompt_name = file_path.stem

                # Load and register the prompt
                prompt = self._create_prompt_from_yaml(str(file_path))
                if prompt:
                    self._prompts[prompt_name] = prompt
                    logger.info(f"Loaded prompt: {prompt_name} from {file_path}")
            except Exception as e:
                logger.error(f"Error loading prompt from {file_path}: {e}")

        logger.info(
            f"Loaded {len(self._prompts)} prompts: {list(self._prompts.keys())}"
        )

    def get(self, name: str) -> Optional[PromptTemplate]:
        """
        Get a prompt by name.

        Args:
            name: The name of the prompt (with namespace prefix if applicable)

        Returns:
            The prompt template or None if not found
        """
        return self._prompts.get(name)

    def list(self, category: Optional[str] = None) -> Dict[str, PromptTemplate]:
        """
        List all available prompts, optionally filtered by category.

        Args:
            category: Optional category to filter by (e.g., 'agents', 'tools')

        Returns:
            Dictionary of prompts
        """
        if category:
            return {
                k: v for k, v in self._prompts.items() if k.startswith(f"{category}.")
            }
        return dict(self._prompts)

    def add(self, name: str, prompt: PromptTemplate):
        """
        Add a prompt to the registry (in-memory only).

        Args:
            name: The name to register the prompt under
            prompt: The prompt object
        """
        self._prompts[name] = prompt


# Create the singleton instance
prompt_registry = PromptRegistry()

# Convenience functions
get_prompt = prompt_registry.get
list_prompts = prompt_registry.list
refresh_prompts = prompt_registry.refresh
