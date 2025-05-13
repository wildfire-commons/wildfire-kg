"""
Centralized logging configuration for the wildfire knowledge graph API.
"""

import logging
from typing import Optional


def setup_logger(verbose: bool = False) -> logging.Logger:
    """
    Set up and configure the application logger.

    Args:
        verbose: Whether to enable verbose logging. If False, only WARNING and above will be shown.

    Returns:
        A configured logger instance
    """
    # Create logger
    logger = logging.getLogger("wildfire_kg")

    # Set level based on verbose flag
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Create console handler if none exists
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("urllib3").setLevel(logging.WARNING)
    # logging.getLogger("openai").setLevel(logging.WARNING)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Optional name for the logger. If None, returns the root wildfire_kg logger.

    Returns:
        A logger instance
    """
    if name:
        return logging.getLogger(f"wildfire_kg.{name}")
    return logging.getLogger("wildfire_kg")
