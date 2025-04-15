"""
Prompts module for loading and managing prompt templates.
"""

from .registry import get_prompt, list_prompts, refresh_prompts, prompt_registry

# Export the main functions
__all__ = [
    "get_prompt",
    "list_prompts",
    "refresh_prompts",
    "prompt_registry",
]
