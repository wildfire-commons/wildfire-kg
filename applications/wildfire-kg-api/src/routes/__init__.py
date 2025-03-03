"""
Routes module for the Wildfire KG API.

This module automatically imports and registers all routers defined in the routes directory.
"""

import importlib
import os
import pkgutil
from typing import Dict

from fastapi import APIRouter, FastAPI

# Route configuration with prefixes - add new routes here
ROUTE_CONFIG = {
    "s3": {"prefix": "/api", "tags": ["S3"]},
    "health": {"prefix": "", "tags": ["Health"]},
    "example": {"prefix": "/api", "tags": ["Examples"]},
    # Add future routes here with their prefixes and tags
}


def get_all_routers() -> Dict[str, APIRouter]:
    """
    Dynamically discover and load all router modules in the routes directory.

    Returns:
        Dict[str, APIRouter]: Dictionary of module_name -> router
    """
    routers = {}
    routes_package = "src.routes"

    # Get the actual path of the routes directory
    routes_path = os.path.dirname(__file__)

    # Find all modules in the routes directory
    for _, module_name, is_package in pkgutil.iter_modules([routes_path]):
        # Skip __init__.py and any packages
        if module_name != "__init__" and not is_package:
            # Import the module
            module = importlib.import_module(f"{routes_package}.{module_name}")

            # If the module has a router attribute, add it to our dict
            if hasattr(module, "router"):
                routers[module_name] = module.router

    return routers


def register_routers(app: FastAPI) -> None:
    """
    Register all routers with the FastAPI app.

    Args:
        app (FastAPI): The FastAPI application
    """
    # Get all routers
    routers = get_all_routers()

    # Register each router with its configuration
    for module_name, router in routers.items():
        # Get configuration for this router, or use empty prefix if not specified
        config = ROUTE_CONFIG.get(module_name, {"prefix": ""})

        # Apply any tags from the configuration
        if "tags" in config and not router.tags:
            router.tags = config["tags"]

        # Include the router with the configured prefix
        app.include_router(router, prefix=config["prefix"])
        print(f"Registered router: {module_name} with prefix '{config['prefix']}'")


# For backwards compatibility - expose the routers directly
# These will be deprecated in the future
from src.routes.s3 import router as s3_router
from src.routes.health import router as health_router
