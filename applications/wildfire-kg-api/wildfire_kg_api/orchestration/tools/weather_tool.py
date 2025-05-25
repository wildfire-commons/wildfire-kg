"""
Weather tool using LangChain's tool decorator.
"""

from typing import Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import os
import requests
import json
from langchain_community.utilities.openweathermap import OpenWeatherMapAPIWrapper

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    try:
        weather_api_key = os.getenv("OPENWEATHERMAP_API_KEY")

        if not weather_api_key:
            logger.warning("No OpenWeatherMap API key provided. Using mock data.")
            return _format_weather_data(_get_mock_weather_data(location), location)

        # Initialize OpenWeatherMap wrapper
        weather = OpenWeatherMapAPIWrapper(openweathermap_api_key=weather_api_key)
        
        # Get weather data
        weather_data = weather.run(location)
        
        # Parse the weather data
        try:
            data = json.loads(weather_data)
            return _format_weather_data(data, location)
        except json.JSONDecodeError:
            # If the data is not in JSON format, return it as is
            return weather_data

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
        if "main" not in data:
            return f"No weather data available for {requested_location}"

        main = data["main"]
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})
        
        # Extract weather elements
        temp_c = main.get("temp", "N/A")
        temp_f = round((temp_c * 9/5) + 32, 1) if isinstance(temp_c, (int, float)) else "N/A"
        condition = weather.get("description", "Unknown")
        humidity = main.get("humidity", "N/A")
        wind_speed_mps = wind.get("speed", "N/A")
        wind_speed_mph = round(wind_speed_mps * 2.237, 1) if isinstance(wind_speed_mps, (int, float)) else "N/A"
        wind_dir = wind.get("deg", "N/A")
        precip_mm = data.get("rain", {}).get("1h", 0)
        precip_in = round(precip_mm / 25.4, 2) if isinstance(precip_mm, (int, float)) else "N/A"

        # Format for wildfire context
        fire_danger = ""
        if (
            isinstance(humidity, (int, float))
            and humidity < 30
            and isinstance(wind_speed_mph, (int, float))
            and wind_speed_mph > 15
        ):
            fire_danger = "\n⚠️ Note: Low humidity and high winds may create elevated fire danger conditions."

        # Build the response
        response = (
            f"🌡️ Weather for {requested_location}:\n"
            f"• Temperature: {temp_f}°F ({temp_c}°C)\n"
            f"• Conditions: {condition}\n"
            f"• Humidity: {humidity}%\n"
            f"• Wind: {wind_speed_mph} mph ({wind_speed_mps} m/s) {wind_dir}°\n"
            f"• Precipitation: {precip_in} in\n"
            f"{fire_danger}"
        )

        # Add air quality if available
        if "air_quality" in data:
            aqi = data["air_quality"]
            aqi_elements = []
            
            for key, value in aqi.items():
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
        "name": location,
        "main": {
            "temp": 25,
            "feels_like": 25,
            "temp_min": 23,
            "temp_max": 27,
            "pressure": 1012,
            "humidity": 45
        },
        "weather": [
            {
                "id": 800,
                "main": "Clear",
                "description": "clear sky",
                "icon": "01d"
            }
        ],
        "wind": {
            "speed": 5.4,
            "deg": 280
        },
        "rain": {
            "1h": 0
        },
        "air_quality": {
            "co": 250.3,
            "no2": 12.4,
            "o3": 97.1,
            "pm2_5": 12.1,
            "pm10": 14.3
        }
    }
