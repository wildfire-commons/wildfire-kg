"""
Weather tool using LangChain's tool decorator.
"""

from typing import Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import os
import requests
import json

from wildfire_kg_api.orchestration.logger import get_logger

# Initialize logger
logger = get_logger("tools.weather")


class WeatherInput(BaseModel):
    """Input for the weather query tool."""

    location: str = Field(
        description="The specific location to check weather for (city, state, country, etc.)"
    )


@tool
def get_weather(location: str) -> str:
    """
    Get current weather information for the specified location.
    Use this tool to check current weather conditions, temperature, humidity, wind speed,
    and other data that might affect wildfire behavior or risk.

    Parameters:
        location: The location to check weather for (city, state, country, etc.)

    Returns:
        A string with formatted weather information.
    """
    logger.info(f"Getting weather for location: {location}")

    # Implementation
    try:
        weather_api_key = os.getenv("WEATHER_API_KEY")
        base_url = "https://api.weatherapi.com/v1"

        if not weather_api_key:
            logger.warning("No Weather API key provided. Using mock data.")
            return _format_weather_data(_get_mock_weather_data(location), location)

        # Make API request
        params = {
            "key": weather_api_key,
            "q": location,
            "aqi": "yes",  # Include air quality data
        }

        logger.debug(f"Making weather API request to {base_url}/current.json")
        response = requests.get(f"{base_url}/current.json", params=params)
        response.raise_for_status()
        weather_data = response.json()
        logger.debug("Weather API request successful")

        return _format_weather_data(weather_data, location)

    except Exception as e:
        logger.error(f"Error in weather query: {str(e)}", exc_info=True)
        # Return mock data on error for graceful degradation
        return (
            _format_weather_data(_get_mock_weather_data(location), location)
            + "\n(Note: Using backup data due to API issue)"
        )


def _format_weather_data(data: Dict[str, Any], requested_location: str) -> str:
    """Format weather data into a human-readable string."""
    try:
        if "current" not in data:
            return f"No weather data available for {requested_location}"

        current = data["current"]
        location_info = data.get("location", {"name": requested_location})
        location_name = location_info.get("name", requested_location)

        # Extract weather elements
        temp_f = current.get("temp_f", "N/A")
        temp_c = current.get("temp_c", "N/A")
        condition = current.get("condition", {}).get("text", "Unknown")
        humidity = current.get("humidity", "N/A")
        wind_mph = current.get("wind_mph", "N/A")
        wind_kph = current.get("wind_kph", "N/A")
        wind_dir = current.get("wind_dir", "N/A")
        precip_in = current.get("precip_in", "N/A")

        # Format for wildfire context
        fire_danger = ""
        if (
            isinstance(humidity, (int, float))
            and humidity < 30
            and isinstance(wind_mph, (int, float))
            and wind_mph > 15
        ):
            fire_danger = "\n⚠️ Note: Low humidity and high winds may create elevated fire danger conditions."

        # Build the response
        response = (
            f"🌡️ Weather for {location_name}:\n"
            f"• Temperature: {temp_f}°F ({temp_c}°C)\n"
            f"• Conditions: {condition}\n"
            f"• Humidity: {humidity}%\n"
            f"• Wind: {wind_mph} mph ({wind_kph} kph) {wind_dir}\n"
            f"• Precipitation: {precip_in} in\n"
            f"{fire_danger}"
        )

        # Add air quality if available
        air_quality = current.get("air_quality", {})
        if air_quality and isinstance(air_quality, dict) and len(air_quality) > 0:
            aqi_elements = []

            for key, value in air_quality.items():
                if key != "us-epa-index" and key != "gb-defra-index":
                    if key == "pm2_5":
                        formatted_key = "PM2.5"
                    elif key == "pm10":
                        formatted_key = "PM10"
                    else:
                        formatted_key = key.upper()

                    aqi_elements.append(f"{formatted_key}: {value}")

            if aqi_elements:
                response += "\n\n🌬️ Air Quality:\n• " + "\n• ".join(aqi_elements)

        return response

    except Exception as e:
        logger.error(f"Error formatting weather data: {str(e)}", exc_info=True)
        return f"Weather information for {requested_location}: {json.dumps(data, indent=2)[:200]}..."


def _get_mock_weather_data(location: str) -> Dict[str, Any]:
    """Return mock weather data for testing or when API is unavailable."""
    return {
        "location": {
            "name": location,
            "region": "Sample Region",
            "country": "United States",
        },
        "current": {
            "temp_c": 25,
            "temp_f": 77,
            "condition": {
                "text": "Sunny",
                "icon": "//cdn.weatherapi.com/weather/64x64/day/113.png",
            },
            "wind_mph": 12,
            "wind_kph": 19.3,
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
            },
        },
    }
