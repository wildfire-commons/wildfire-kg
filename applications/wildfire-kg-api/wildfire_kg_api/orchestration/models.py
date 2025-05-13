"""
Configuration for available LLM models.
"""

# Dictionary of all available models with their configurations
MODEL_CONFIGS = {
    # LiteLLM models
    "DeepSeek-R1-Distill-Qwen-32B": {
        "provider": "litellm",
        "default_temperature": 0.0,
        "agent_compatible": False,  # Does not support automatic tool choice
    },
    "gemma3": {
        "provider": "litellm",
        "default_temperature": 0.0,
        "agent_compatible": True,
    },
    "groq-tools": {
        "provider": "litellm",
        "default_temperature": 0.0,
        "agent_compatible": True,
    },
    "llama3": {
        "provider": "litellm",
        "default_temperature": 0.0,
        "agent_compatible": True,
    },
    # OpenAI models
    "gpt-4o": {
        "provider": "openai",
        "default_temperature": 0.0,
        "agent_compatible": True,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "default_temperature": 0.0,
        "agent_compatible": True,
    },
    "o4-mini": {
        "provider": "openai",
        "default_temperature": 0.0,
        "agent_compatible": True,
    },
}

# Convenience lists (derived from the MODEL_CONFIGS dictionary)
AVAILABLE_MODELS = list(MODEL_CONFIGS.keys())
LITELLM_MODELS = [
    model for model, config in MODEL_CONFIGS.items() if config["provider"] == "litellm"
]
OPENAI_MODELS = [
    model for model, config in MODEL_CONFIGS.items() if config["provider"] == "openai"
]
AGENT_COMPATIBLE_MODELS = [
    model
    for model, config in MODEL_CONFIGS.items()
    if config.get("agent_compatible", False)
]

# Fallback model configuration for the agent and tools
BEST_MODEL_FALLBACK = {
    "agent": {
        "model": "llama3",
        "temperature": 0.0,
    },
    "kg_tool": {
        "model": "llama3",
        "temperature": 0.0,
    },
    # "web_search_tool": {
    #     "model": "llama3",
    #     "temperature": 0.0,
    # },
    # "weather_tool": {
    #     "model": "llama3",
    #     "temperature": 0.0,
    # },
}


def is_openai_model(model_name: str) -> bool:
    """
    Determine if a model is from OpenAI based on its entry in MODEL_CONFIGS.

    Args:
        model_name: The name of the model

    Returns:
        True if the model is from OpenAI, False otherwise
    """
    return MODEL_CONFIGS.get(model_name, {}).get("provider", "litellm") == "openai"


def get_default_temperature(model_name: str) -> float:
    """
    Get the default temperature for a given model.

    Args:
        model_name: The name of the model

    Returns:
        The default temperature for the model, or 0.0 if not found
    """
    return MODEL_CONFIGS.get(model_name, {}).get("default_temperature", 0.0)


def is_agent_compatible(model_name: str) -> bool:
    """
    Determine if a model is compatible with the ReAct agent pattern.

    Args:
        model_name: The name of the model

    Returns:
        True if the model is compatible with the ReAct agent, False otherwise
    """
    return MODEL_CONFIGS.get(model_name, {}).get("agent_compatible", False)
