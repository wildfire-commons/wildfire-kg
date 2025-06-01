"""
Weather tool using LangChain's tool decorator.
"""

from typing import Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import os
import requests
import json
import re
from datetime import datetime, timedelta
import dateparser
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("WEATHER_API_KEY")
if not API_KEY:
    logger.warning("WEATHER_API_KEY environment variable is not set! Historical and current weather API calls will fail.")
PRO_BASE_URL = "https://pro.openweathermap.org/data/2.5/weather"
HIST_BASE_URL = "https://history.openweathermap.org/data/2.5/history/city"

class WeatherInput(BaseModel):
    """Input for the weather query tool."""

    location: str = Field(
        description="The specific location to check weather for (city, state, country, etc.)"
    )


@tool
def get_weather(query: str) -> str:
    """
    Get current or historical weather information for the specified location, with a focus on wildfire behavior and risk.

    This tool provides:
    - A detailed weather summary (temperature, humidity, wind, precipitation, etc.)
    - A wildfire risk assessment based on the weather conditions (e.g., dryness, wind, humidity, temperature, precipitation)
    - Actionable recommendations if conditions are favorable or unfavorable for wildfire ignition or spread
    - For historical queries, includes the date range and data source

    Output Outline:
    1. Weather Summary
        - Date (or date range for historical)
        - Location
        - Temperature (°F/°C)
        - Humidity (%)
        - Wind (mph/m/s, direction)
        - Precipitation (inches)
        - Conditions (e.g., clear, overcast, rain)
    2. Wildfire Risk Assessment
        - Explanation of how the weather affects wildfire risk (e.g., "High winds and low humidity increase fire danger.")
        - Highlight any factors that increase or decrease risk
    3. Recommendations (if applicable)
        - E.g., "Exercise caution with open flames. Avoid outdoor burning."
    4. Data Source/Date Range (for historical queries)

    Example Output (Current):
    -------------------------
    🌡️ Weather for San Diego, CA (July 20, 2024):
    • Temperature: 92.3°F (33.5°C)
    • Conditions: Sunny
    • Humidity: 18%
    • Wind: 17.2 mph (7.7 m/s) 270°
    • Precipitation: 0.0 in

    🔥 Wildfire Risk Assessment:
    • Low humidity and high winds create elevated fire danger conditions. Fine fuels may ignite easily and fires can spread rapidly.

    ⚠️ Recommendation:
    • Avoid outdoor burning and use caution with open flames.

    Example Output (Historical):
    ----------------------------
    📅 Historical Weather for San Diego, CA (September 3, 2023):
    • Avg Temperature: 58.8°F (14.9°C)
    • Avg Humidity: 85%
    • Avg Wind Speed: 5.0 mph (2.2 m/s)
    • Precipitation: 0.0 in

    🔥 Wildfire Risk Assessment:
    • High humidity and cooler temperatures reduce fire danger. Conditions are generally unfavorable for wildfire ignition and spread.

    Data Source: OpenWeatherMap Historical API (hourly data)
    Date Range: 2023-09-03 00:00 to 2023-09-03 23:59 UTC

    Parameters:
        query: The full user query including location and date
    """
    logger.info(f"Getting weather for query: {query}")
    try:
        date = extract_date_from_query(query)
        location = extract_location_from_query(query)
        today = datetime.utcnow().date()

        # Determine if this is a historical query
        is_historical = date and date.date() != today
        logger.info(f"Query type: {'Historical' if is_historical else 'Current'}")
        logger.info(f"Date: {date}, Location: {location}")

        # For future dates, return an error
        if date and date.date() > today:
            return f"❌ Cannot provide weather data for future dates. Requested date: {date.date()}, today: {today}"

        # For historical queries, check if within supported range (OpenWeatherMap only supports up to 5 days back for some plans)
        if is_historical:
            days_ago = (today - date.date()).days
            if days_ago > 5:
                return (
                    f"❌ Sorry, historical weather data is only available for the past 5 days. "
                    f"Requested date: {date.date()}, today: {today}."
                )

        def try_weather_api(loc, is_historical):
            if is_historical:
                # First get the city ID
                city_id = _get_city_id(loc)
                if not city_id:
                    logger.error(f"Could not find city ID for {loc}")
                    return None, f"Could not find city ID for {loc}."

                # Calculate timestamps for the requested date
                start = int(datetime(date.year, date.month, date.day, 0, 0).timestamp())
                end = int(datetime(date.year, date.month, date.day, 23, 59, 59).timestamp())

                # Make the historical API call
                params = {
                    "id": city_id,
                    "type": "hour",
                    "start": start,
                    "end": end,
                    "appid": API_KEY,
                    "units": "metric"
                }
                logger.info(f"Making historical API call to {HIST_BASE_URL} with params: {params}")

                try:
                    response = requests.get(HIST_BASE_URL, params=params)
                    logger.info(f"Historical API response status: {response.status_code}")
                    logger.info(f"Historical API response headers: {response.headers}")

                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"Historical API response data: {json.dumps(data)[:200]}...")
                        logger.info(f"Raw historical API response: {json.dumps(data)[:1000]}")

                        if "list" in data and data["list"]:
                            return _format_historical_weather_data(data, loc, date), None
                        else:
                            logger.error(f"No historical data found in response for {loc} on {date.date()}")
                            return None, f"No historical weather data available for {loc} on {date.date()}."
                    else:
                        logger.error(f"Historical API error: {response.status_code} - {response.text}")
                        return None, f"Historical weather not found for {loc}. API Error: {response.status_code}"
                except Exception as e:
                    logger.error(f"Error making historical API call: {str(e)}")
                    return None, f"Error retrieving historical weather data: {str(e)}"
            else:
                # Current weather API call
                params = {
                    "q": loc,
                    "appid": API_KEY,
                    "units": "metric"
                }
                logger.info(f"Making current weather API call to {PRO_BASE_URL} with params: {params}")

                try:
                    response = requests.get(PRO_BASE_URL, params=params)
                    logger.info(f"Current weather API response status: {response.status_code}")
                    logger.info(f"Current weather API response headers: {response.headers}")

                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"Current weather API response data: {json.dumps(data)[:200]}...")
                        return _format_weather_data(data, loc), None
                    else:
                        logger.error(f"Current weather API error: {response.status_code} - {response.text}")
                        return None, f"Current weather not found for {loc}. API Error: {response.status_code}"
                except Exception as e:
                    logger.error(f"Error making current weather API call: {str(e)}")
                    return None, f"Error retrieving current weather data: {str(e)}"

        # Try "City, State" first
        result, error = try_weather_api(location, is_historical)
        if result:
            return result

        # If "City, State" fails, try just "City"
        if "," in location:
            city_only = location.split(",")[0].strip()
            logger.info(f"Trying city-only location: {city_only}")
            result, error = try_weather_api(city_only, is_historical)
            if result:
                return result

        # If this was a historical query, do NOT fallback to current weather
        if is_historical:
            return error or (
                f"❌ Historical weather data is unavailable for {location} on {date.date()}. "
                "This may be due to API limitations (only last 5 days supported) or city not found."
            )

        # If all fails for current weather
        return error or f"Weather information for {location} is unavailable."

    except Exception as e:
        logger.error(f"Error in weather query: {str(e)}", exc_info=True)
        return f"Weather information for {query} is unavailable. Error: {str(e)}"


def _get_city_id(city: str) -> str:
    """Get the OpenWeatherMap city ID for a given city name."""
    try:
        # Try different city name formats
        city_formats = [
            city,  # Original format
            city.split(",")[0].strip() if "," in city else None,  # Just city name
            f"{city},US" if "," not in city else None,  # Add country code
        ]
        
        # Remove None values
        city_formats = [fmt for fmt in city_formats if fmt]
        
        for city_format in city_formats:
            params = {
                "q": city_format,
                "appid": API_KEY
            }
            logger.info(f"Trying to get city ID for format: {city_format} with params: {params}")
            
            response = requests.get(PRO_BASE_URL, params=params)
            logger.info(f"City ID API response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                city_id = str(data.get("id"))
                if city_id:
                    logger.info(f"Found city ID: {city_id} for {city_format}")
                    return city_id
                else:
                    logger.warning(f"No city ID found in response for {city_format}")
            else:
                logger.warning(f"Failed to get city ID for {city_format}: {response.status_code} - {response.text}")
        
        logger.error(f"Could not find city ID for any format of {city}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting city ID: {str(e)}", exc_info=True)
        return None


def _format_weather_data(data: Dict[str, Any], requested_location: str) -> str:
    """Format weather data into a human-readable string."""
    try:
        if "main" not in data:
            return f"No weather data available for {requested_location}"
        main = data["main"]
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})
        temp_c = main.get("temp", "N/A")
        temp_f = round((temp_c * 9/5) + 32, 1) if isinstance(temp_c, (int, float)) else "N/A"
        condition = weather.get("description", "Unknown")
        humidity = main.get("humidity", "N/A")
        wind_speed_mps = wind.get("speed", "N/A")
        wind_speed_mph = round(wind_speed_mps * 2.237, 1) if isinstance(wind_speed_mps, (int, float)) else "N/A"
        wind_dir = wind.get("deg", "N/A")
        precip_mm = data.get("rain", {}).get("1h", 0)
        precip_in = round(precip_mm / 25.4, 2) if isinstance(precip_mm, (int, float)) else "N/A"
        fire_danger = ""
        if (
            isinstance(humidity, (int, float))
            and humidity < 30
            and isinstance(wind_speed_mph, (int, float))
            and wind_speed_mph > 15
        ):
            fire_danger = "\n⚠️ Note: Low humidity and high winds may create elevated fire danger conditions."
        response = (
            f"🌡️ Weather for {requested_location}:\n"
            f"• Temperature: {temp_f}°F ({temp_c}°C)\n"
            f"• Conditions: {condition}\n"
            f"• Humidity: {humidity}%\n"
            f"• Wind: {wind_speed_mph} mph ({wind_speed_mps} m/s) {wind_dir}°\n"
            f"• Precipitation: {precip_in} in\n"
            f"{fire_danger}"
        )
        return response
    except Exception as e:
        logger.error(f"Error formatting weather data: {str(e)}", exc_info=True)
        return f"Weather information for {requested_location}: {json.dumps(data, indent=2)[:200]}..."


def _format_historical_weather_data(data: Dict[str, Any], city: str, date: datetime) -> str:
    """Format historical weather data into a human-readable string, with debug logging and date validation."""
    try:
        if "list" not in data or not data["list"]:
            logger.error(f"No historical data list found in response for {city}")
            return f"No historical weather data available for {city}."

        # Debug: log all timestamps in the returned data
        timestamps = [entry.get("dt") for entry in data["list"] if "dt" in entry]
        readable_times = [datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M') for ts in timestamps if ts]
        logger.info(f"Historical API returned timestamps: {readable_times}")

        # Validate that at least one entry matches the requested date
        requested_date_str = date.strftime('%Y-%m-%d')
        has_matching_date = any(datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d') == requested_date_str for ts in timestamps if ts)
        if not has_matching_date:
            logger.error(f"Historical API did not return data for requested date {requested_date_str}. Returned dates: {set([datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d') for ts in timestamps if ts])}")
            return f"❌ Historical weather data is unavailable for {city} on {requested_date_str}. The API did not return data for this date."

        # Calculate averages from hourly data for the requested date only
        temps = []
        humidities = []
        wind_speeds = []
        precipitations = []
        conditions = {}

        for entry in data["list"]:
            ts = entry.get("dt")
            if ts and datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d') != requested_date_str:
                continue  # skip entries not for the requested date
            if "main" in entry:
                temps.append(entry["main"].get("temp", 0))
                humidities.append(entry["main"].get("humidity", 0))
            if "wind" in entry:
                wind_speeds.append(entry["wind"].get("speed", 0))
            if "rain" in entry:
                precipitations.append(entry["rain"].get("1h", 0))
            if "weather" in entry and entry["weather"]:
                condition = entry["weather"][0].get("description", "unknown")
                conditions[condition] = conditions.get(condition, 0) + 1

        # Calculate averages
        avg_temp = round(sum(temps)/len(temps), 1) if temps else "N/A"
        avg_humidity = round(sum(humidities)/len(humidities), 1) if humidities else "N/A"
        avg_wind = round(sum(wind_speeds)/len(wind_speeds), 1) if wind_speeds else "N/A"
        avg_precip = round(sum(precipitations)/len(precipitations), 2) if precipitations else 0

        # Convert temperature to Fahrenheit
        avg_temp_f = round((avg_temp * 9/5) + 32, 1) if isinstance(avg_temp, (int, float)) else "N/A"
        
        # Get most common condition
        most_common_condition = max(conditions.items(), key=lambda x: x[1])[0] if conditions else "unknown"

        # Format the response
        response = (
            f"📅 Historical Weather for {city} on {date.strftime('%B %d, %Y')}:\n"
            f"• Average Temperature: {avg_temp_f}°F ({avg_temp}°C)\n"
            f"• Average Humidity: {avg_humidity}%\n"
            f"• Average Wind Speed: {avg_wind} m/s\n"
            f"• Average Precipitation: {avg_precip} mm\n"
            f"• Most Common Condition: {most_common_condition}\n"
            f"\nData Source: OpenWeatherMap Historical API"
        )

        # Add wildfire risk assessment
        if isinstance(avg_humidity, (int, float)) and isinstance(avg_wind, (int, float)):
            if avg_humidity < 30 and avg_wind > 5:
                response += "\n\n🔥 Wildfire Risk Assessment:\n• Low humidity and moderate winds indicate elevated fire danger."
            elif avg_humidity > 70:
                response += "\n\n🔥 Wildfire Risk Assessment:\n• High humidity reduces fire danger."

        return response

    except Exception as e:
        logger.error(f"Error formatting historical weather data: {str(e)}", exc_info=True)
        return f"Error processing historical weather data for {city}: {str(e)}"


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

def extract_date_from_query(query):
    # Try to parse a date from the query string
    date = dateparser.parse(query, settings={'PREFER_DATES_FROM': 'past'})
    return date

def extract_location_from_query(query):
    # Remove common leading phrases
    cleaned = re.sub(r"^(current|historical)?\s*weather\s*(in|for|at)?\s*", "", query, flags=re.IGNORECASE)
    # Try to extract "City, State"
    match = re.search(r"([A-Za-z ]+),\s*[A-Za-z]{2}", cleaned)
    if match:
        return match.group(0).strip()
    # Try just "City"
    match = re.search(r"([A-Za-z ]+)", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned.strip()  # fallback
