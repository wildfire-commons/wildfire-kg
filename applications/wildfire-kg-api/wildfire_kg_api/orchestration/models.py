"""
Configuration for available LLM models.
"""

from typing import Dict, Optional, Any
import os

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
        "agent_compatible": False,  # NOTE: This model requires some server side flags to enable auto-tool selection
    },
    "llama3-sdsc": {
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
        "default_temperature": None,  # o4-mini may not support temperature
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

# Fallback model configuration for the agent and tools defaulting to Litellm models
BEST_MODEL_FALLBACK = {
    "agent": {
        "model": "llama3-sdsc",
        #"model": "gpt-4o",
        "temperature": 0.0,
    },
    "kg_tool": {
        "model": "llama3-sdsc",
        "temperature": 0.0,
    },
    # "web_search_tool": {
    #     "model": "llama3",
    #     "temperature": 0.0,
    # },
    #"weather_tool": {
    #    "model": "gpt-4o",
    #    "temperature": 0.0,
    #},
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


def get_default_temperature(model_name: str) -> Optional[float]:
    """
    Get the default temperature for a given model.

    Args:
        model_name: The name of the model

    Returns:
        The default temperature for the model, or None if not found or not applicable.
    """
    model_config = MODEL_CONFIGS.get(model_name, {})
    return model_config.get("default_temperature")


def is_agent_compatible(model_name: str) -> bool:
    """
    Determine if a model is compatible with the ReAct agent pattern.

    Args:
        model_name: The name of the model

    Returns:
        True if the model is compatible with the ReAct agent, False otherwise
    """
    return MODEL_CONFIGS.get(model_name, {}).get("agent_compatible", False)


def get_llm_params_for_model(
    model_name: str,
    temperature_override: Optional[float] = None,
    **additional_kwargs: Any,
) -> Dict[str, Any]:
    """
    Constructs the language model parameters dictionary for a given model.

    It conditionally includes the 'temperature' parameter based on the model's
    configuration and any override provided.

    Args:
        model_name: The name of the model.
        temperature_override: An optional temperature value to use instead of
                              the model's default. If the model does not support
                              temperature, this will be ignored.
        **additional_kwargs: Other parameters to include in the LLM configuration
                             (e.g., callbacks, tags, api_key, openai_api_base).

    Returns:
        A dictionary of parameters suitable for initializing a ChatOpenAI client.
    """
    model_config = MODEL_CONFIGS.get(model_name)
    if not model_config:
        # Fallback to a generic config if model_name is not in MODEL_CONFIGS
        # This might happen if a model string is passed directly
        # For simplicity, assume it's an OpenAI model and might support temperature
        # A more robust solution would raise an error or have better defaults
        model_config = {
            "provider": "openai",  # Default assumption
            "default_temperature": 0.0,  # Default assumption
        }
        # Log a warning if a model not in MODEL_CONFIGS is used.
        # Consider adding a logger instance if you have one configured.
        # print(f"Warning: Model '{model_name}' not found in MODEL_CONFIGS. Using default assumptions.")

    params: Dict[str, Any] = {"model": model_name}
    params.update(additional_kwargs)

    # Determine the temperature
    effective_temperature: Optional[float] = None
    model_default_temp = model_config.get("default_temperature")

    if temperature_override is not None:
        if model_default_temp is not None:  # Model supports temperature
            effective_temperature = temperature_override
        # If model_default_temp is None, it means model doesn't support temp,
        # so we don't set effective_temperature even if override is provided.
    elif model_default_temp is not None:
        effective_temperature = model_default_temp

    if effective_temperature is not None:
        params["temperature"] = effective_temperature

    # Add provider-specific parameters
    if model_config.get("provider") == "openai":
        if "api_key" not in params and os.getenv("OPENAI_API_KEY"):
            params["api_key"] = os.getenv("OPENAI_API_KEY")
    else:  # Assuming litellm or other providers that use openai_api_base
        if "openai_api_base" not in params and os.getenv("LITELLM_BASE_URL"):
            params["openai_api_base"] = os.getenv("LITELLM_BASE_URL")
        if "api_key" not in params and os.getenv(
            "LITELLM_API_KEY"
        ):  # LiteLLM also uses api_key
            params["api_key"] = os.getenv("LITELLM_API_KEY")

    return params
