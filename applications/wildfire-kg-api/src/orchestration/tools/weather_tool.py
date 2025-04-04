from typing import Dict, List, Any, Optional, Type
import logging
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import os
from datetime import datetime
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeatherQueryInput(BaseModel):
    """Input for the weather query tool."""
    query: str = Field(description="The natural language query about weather conditions")
    location: Optional[str] = Field(description="Specific location to check weather for")


class WeatherTool(BaseTool):
    """Tool for retrieving weather information using a weather API."""

    name: str = "weather_query"
    description: str = """
    Use this tool to get weather information and conditions.
    This is useful for checking current weather conditions, forecasts, and historical weather data
    that might affect wildfire behavior or risk.
    """
    args_schema: Type[WeatherQueryInput] = WeatherQueryInput

    # Define the fields properly
    weather_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("WEATHER_API_KEY")
    )
    base_url: str = "https://api.weatherapi.com/v1"  # Example using WeatherAPI.com

    def __init__(self, weather_api_key: Optional[str] = None, **kwargs):
        """Initialize the weather tool."""
        api_key = weather_api_key or os.getenv("WEATHER_API_KEY")
        super().__init__(weather_api_key=api_key, **kwargs)

        if not api_key:
            logger.warning("No Weather API key provided. Weather data will be mocked.")

    def _run(self, query: str, location: Optional[str] = None) -> Dict[str, Any]:
        """Run the tool."""
        start_time = datetime.now()

        logger.info(f"Querying weather data for: {query} (location: {location})")

        try:
            if not self.weather_api_key:
                # Return mock data if no API key is available
                return self._get_mock_weather_data(location)

            # Extract location from query if not provided
            if not location:
                # You could use NLP here to extract location, for now just use a default
                location = "California"  # Default to California for wildfire context

            # Make API request
            params = {
                "key": self.weather_api_key,
                "q": location,
                "aqi": "yes"  # Include air quality data
            }
            
            response = requests.get(f"{self.base_url}/current.json", params=params)
            response.raise_for_status()
            weather_data = response.json()

            # Calculate execution time
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            # Format the response
            return {
                "query": query,
                "location": location,
                "weather_data": weather_data,
                "execution_time": execution_time
            }

        except Exception as e:
            logger.error(f"Error in weather query: {str(e)}", exc_info=True)
            return {
                "query": query,
                "location": location,
                "error": str(e),
                "weather_data": self._get_mock_weather_data(location),
                "execution_time": 0.0
            }

    def _get_mock_weather_data(self, location: Optional[str] = None) -> Dict[str, Any]:
        """Return mock weather data for testing or when API is unavailable."""
        return {
            "location": {
                "name": location or "California",
                "region": "California",
                "country": "United States of America",
            },
            "current": {
                "temp_c": 25,
                "temp_f": 77,
                "condition": {
                    "text": "Sunny",
                    "icon": "//cdn.weatherapi.com/weather/64x64/day/113.png"
                },
                "wind_mph": 12,
                "wind_kph": 19.3,
                "wind_degree": 280,
                "wind_dir": "W",
                "pressure_mb": 1012,
                "pressure_in": 29.89,
                "precip_mm": 0,
                "precip_in": 0,
                "humidity": 45,
                "cloud": 0,
                "feelslike_c": 25,
                "feelslike_f": 77,
                "vis_km": 10,
                "vis_miles": 6,
                "uv": 6,
                "gust_mph": 13.6,
                "gust_kph": 22,
                "air_quality": {
                    "co": 250.3,
                    "no2": 12.4,
                    "o3": 97.1,
                    "pm2_5": 12.1,
                    "pm10": 14.3,
                }
            }
        }

    async def _arun(self, query: str, location: Optional[str] = None) -> Dict[str, Any]:
        """Run the tool asynchronously."""
        # For simplicity, we'll just call the synchronous version
        return self._run(query, location) 