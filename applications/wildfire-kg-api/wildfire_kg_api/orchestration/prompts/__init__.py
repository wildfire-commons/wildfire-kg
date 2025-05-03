"""
Prompts module for loading and managing prompt templates.
"""

from wildfire_kg_api.orchestration.prompts.prompt_registry import (
    get_prompt,
    list_prompts,
    refresh_prompts,
    prompt_registry,
)

# Export the main functions
__all__ = [
    "get_prompt",
    "list_prompts",
    "refresh_prompts",
    "prompt_registry",
]
