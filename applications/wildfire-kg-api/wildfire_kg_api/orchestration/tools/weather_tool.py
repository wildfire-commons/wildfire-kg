"""
Weather tool using LangChain's tool decorator.
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import json
import re
import dateparser
import urllib.parse
import sys

# Configure logging to write to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Force the logger to output to stdout
for handler in logger.handlers:
    handler.setStream(sys.stdout)

file_handler = logging.FileHandler("weather_tool_debug.log")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

API_KEY = os.getenv("WEATHER_API_KEY")
if not API_KEY:
    logger.warning(
        "WEATHER_API_KEY environment variable is not set! Historical and current weather API calls will fail."
    )
PRO_BASE_URL = "https://pro.openweathermap.org/data/2.5/weather"
HIST_BASE_URL = "https://history.openweathermap.org/data/2.5/history/city"
FORECAST_BASE_URL = "https://pro.openweathermap.org/data/2.5/forecast"
GEOCODE_URL = "http://api.openweathermap.org/geo/1.0/direct"

# US state abbreviation to full name mapping
US_STATE_ABBR = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


class WeatherInput(BaseModel):
    """Input for the weather query tool."""

    location: str = Field(
        description="The specific location to check weather for (city, state, country, etc.)"
    )


def geocode_location(location: str) -> Optional[dict]:
    """Use OpenWeatherMap geocoding API to resolve a location string to lat/lon and city id. Try fallbacks for US cities."""
    attempts = [location]
    # If location ends with ', XX' where XX is a US state abbreviation, try fallbacks
    m = re.match(r"^(.*),\s*([A-Za-z]{2})$", location.strip())
    if m:
        city = m.group(1).strip()
        state_abbr = m.group(2).upper()
        if state_abbr in US_STATE_ABBR:
            # Try 'City, US' and 'City, FullStateName, US'
            attempts.append(f"{city}, US")
            attempts.append(f"{city}, {US_STATE_ABBR[state_abbr]}, US")
    # Always try 'City, USA' as a last resort
    if not location.strip().lower().endswith(", usa"):
        attempts.append(location.strip() + ", USA")
    logger.info(f"Geocoding attempts: {attempts}")
    for attempt in attempts:
        params = {"q": attempt, "limit": 1, "appid": API_KEY}
        logger.info(f"Geocoding location: {attempt}")
        resp = requests.get(GEOCODE_URL, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                logger.info(f"Geocoding result: {data[0]}")
                return data[0]
            else:
                logger.warning(f"No geocoding result for {attempt}")
        else:
            logger.warning(
                f"Geocoding failed for {attempt}: {resp.status_code} - {resp.text}"
            )
    return None


def _sanitize_params_for_logging(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a sanitized copy of params for logging that masks sensitive information."""
    sanitized = params.copy()
    if "appid" in sanitized:
        # Mask the API key for logging - show first 4 and last 4 characters with asterisks in between
        api_key = sanitized["appid"]
        if len(api_key) > 8:
            sanitized["appid"] = (
                f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"
            )
        else:
            sanitized["appid"] = "*" * len(api_key)
    return sanitized


def _log_api_call(
    base_url: str, params: Dict[str, Any], response: requests.Response
) -> None:
    """Log API call details and response."""
    sanitized_params = _sanitize_params_for_logging(params)
    print(f"\n{'='*50}\nAPI Call Details:", flush=True)
    print(f"Endpoint: {base_url}", flush=True)
    print(f"Parameters: {json.dumps(sanitized_params, indent=2)}", flush=True)
    print(f"Status Code: {response.status_code}", flush=True)
    try:
        print(
            f"Response: {json.dumps(response.json(), indent=2)}\n{'='*50}\n", flush=True
        )
    except:
        print(f"Response: {response.text}\n{'='*50}\n", flush=True)


def _call_weather_api(endpoint, params, query_type, city_label):
    """Call weather API with logging."""
    sanitized_params = _sanitize_params_for_logging(params)
    logger.info(
        f"Calling {query_type} endpoint: {endpoint} with params: {sanitized_params}"
    )
    response = requests.get(endpoint, params=params)
    _log_api_call(endpoint, params, response)
    if response.status_code == 200:
        data = response.json()
        logger.info(f"API response for {city_label}: {json.dumps(data)[:200]}...")
        return data
    else:
        logger.warning(
            f"API error for {city_label}: {response.status_code} - {response.text}"
        )
        return None


@tool
def get_weather(query: str) -> str:
    """
    Get current, historical, or forecast weather information for the specified location, with a focus on wildfire behavior and risk.

    This tool provides:
    - A detailed weather summary (temperature, humidity, wind, precipitation, etc.)
    - A wildfire risk assessment based on the weather conditions (e.g., dryness, wind, humidity, temperature, precipitation)

    INSTRUCTIONS FOR THE AGENT:
    1. **Extract the location** (city, state, country) from the query.
    2. **Extract the date** (if present) from the query.
    3. **Determine the type of weather query:**
        - If the date is today or not specified, use the **current weather** endpoint.
        - If the date is in the past (within the last 5 days), use the **historical weather** endpoint.
        - If the date is in the future (within the next 5 days), use the **forecast weather** endpoint.
    4. **Call the appropriate endpoint** with the resolved location and date.
    5. **Return a detailed weather summary** and a wildfire risk assessment.

    Example queries and endpoint selection:
    - "current weather in San Diego, CA" → current weather endpoint
    - "historical weather for San Diego, CA on May 23, 2025" → historical weather endpoint
    - "forecast weather for San Diego, CA on May 27, 2025" → forecast weather endpoint

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

    Output should include:
    - Date and location
    - Temperature, humidity, wind, precipitation, and conditions
    - Wildfire risk assessment and recommendations

    Parameters:
        query: The full user query including location and date
    """
    logger.info(f"\n{'='*50}\nProcessing weather query: {query}")
    try:
        date = extract_date_from_query(query)
        location = extract_location_from_query(query)
        today = datetime.utcnow().date()

        is_historical = date and date.date() < today
        is_forecast = date and date.date() > today
        is_current = not date or date.date() == today

        logger.info(f"Query Analysis:")
        logger.info(f"- Date: {date}")
        logger.info(f"- Location: {location}")
        logger.info(
            f"- Type: {'Historical' if is_historical else 'Forecast' if is_forecast else 'Current'}"
        )

        # Geocode location ONCE
        geo = geocode_location(location)
        if not geo:
            return (
                f"Could not resolve location '{location}'. Please check the city name."
            )
        lat, lon = geo["lat"], geo["lon"]
        city_label = geo.get("name", location)
        city_id = geo.get("id")  # Not always present

        # Use city_id if available, else lat/lon
        params = {"appid": API_KEY, "units": "metric"}
        if city_id:
            params["id"] = city_id
        else:
            params["lat"] = lat
            params["lon"] = lon

        if is_forecast:
            logger.info("Making forecast API call...")
            data = _call_weather_api(FORECAST_BASE_URL, params, "forecast", city_label)
            if not data:
                return f"No forecast weather data available for {city_label}."
            return _format_forecast_weather_data(data, city_label, date)

        if is_historical:
            start = int(datetime(date.year, date.month, date.day, 0, 0).timestamp())
            end = int(datetime(date.year, date.month, date.day, 23, 59, 59).timestamp())
            params.update({"type": "hour", "start": start, "end": end})
            logger.info("Making historical API call...")
            data = _call_weather_api(HIST_BASE_URL, params, "historical", city_label)
            if not data:
                return f"No historical weather data available for {city_label} on {date.date()}."
            return _format_historical_weather_data(data, city_label, date)

        # Default to current weather
        logger.info("Making current weather API call...")
        data = _call_weather_api(PRO_BASE_URL, params, "current", city_label)
        if not data:
            return f"No current weather data available for {city_label}."
        return _format_weather_data(data, city_label)
    except Exception as e:
        logger.error(f"Error in weather query: {str(e)}", exc_info=True)
        return f"Weather information for {query} is unavailable. Error: {str(e)}"


def _format_weather_data(data: Dict[str, Any], requested_location: str) -> str:
    """Format weather data into a human-readable string."""
    try:
        if "main" not in data:
            return f"No weather data available for {requested_location}"
        main = data["main"]
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})
        temp_c = main.get("temp", "N/A")
        temp_f = (
            round((temp_c * 9 / 5) + 32, 1)
            if isinstance(temp_c, (int, float))
            else "N/A"
        )
        condition = weather.get("description", "Unknown")
        humidity = main.get("humidity", "N/A")
        wind_speed_mps = wind.get("speed", "N/A")
        wind_speed_mph = (
            round(wind_speed_mps * 2.237, 1)
            if isinstance(wind_speed_mps, (int, float))
            else "N/A"
        )
        wind_dir = wind.get("deg", "N/A")
        precip_mm = data.get("rain", {}).get("1h", 0)
        precip_in = (
            round(precip_mm / 25.4, 2) if isinstance(precip_mm, (int, float)) else "N/A"
        )
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


def _format_historical_weather_data(data, city, date):
    entries = data.get("list", [])
    requested_date_str = date.strftime("%Y-%m-%d")
    filtered = [
        e
        for e in entries
        if datetime.utcfromtimestamp(e["dt"]).strftime("%Y-%m-%d") == requested_date_str
    ]
    logger.info(
        f"Averaging {len(filtered)} historical entries for {city} on {requested_date_str}"
    )
    if not filtered:
        return f"No historical weather data available for {city} on {date.date()}."
    temps = [e["main"]["temp"] for e in filtered]
    humidities = [e["main"]["humidity"] for e in filtered]
    winds = [e["wind"]["speed"] for e in filtered]
    avg_temp = sum(temps) / len(temps)
    avg_humidity = sum(humidities) / len(humidities)
    avg_wind = sum(winds) / len(winds)
    avg_temp_f = (avg_temp * 9 / 5) + 32
    return (
        f"📅 Historical Weather for {city} ({date.strftime('%B %d, %Y')}):\n"
        f"- Avg Temperature: {avg_temp_f:.1f}°F ({avg_temp:.1f}°C)\n"
        f"- Avg Humidity: {avg_humidity:.0f}%\n"
        f"- Avg Wind: {avg_wind:.2f} m/s\n"
    )


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
            "humidity": 45,
        },
        "weather": [
            {"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}
        ],
        "wind": {"speed": 5.4, "deg": 280},
        "rain": {"1h": 0},
        "air_quality": {
            "co": 250.3,
            "no2": 12.4,
            "o3": 97.1,
            "pm2_5": 12.1,
            "pm10": 14.3,
        },
    }


def extract_date_from_query(query):
    # Try to extract a date after the last 'on', 'for', or 'at'
    match = re.search(r"(?:on|for|at)\s+([A-Za-z0-9, ]*\d{4})", query, re.IGNORECASE)
    if match:
        date_str = match.group(1).strip()
        # Remove any trailing location info (e.g., "San Diego, CA on May 23, 2025")
        date_only = re.sub(r"^[A-Za-z\s,]*", "", date_str)
        parsed = dateparser.parse(date_only)
        logger.info(f"Extracted date from explicit pattern: {date_only} -> {parsed}")
        if parsed:
            return parsed

    # Fallback: use dateparser's search_dates to find any date in the string
    try:
        from dateparser.search import search_dates

        found = search_dates(query)
        if found:
            # Pick the last date found (usually the most relevant)
            logger.info(f"Extracted date using search_dates: {found[-1][1]}")
            return found[-1][1]
    except Exception as e:
        logger.warning(f"dateparser.search_dates failed: {e}")

    # If "current" in query, return today
    if "current" in query.lower():
        today = datetime.utcnow()
        logger.info(f"Query is for current weather, using today: {today}")
        return today

    # If "historical" in query, but no date, return yesterday
    if "historical" in query.lower():
        yesterday = datetime.utcnow() - timedelta(days=1)
        logger.info(f"Query is for historical weather, using yesterday: {yesterday}")
        return yesterday

    # If "forecast" in query, but no date, return tomorrow
    if "forecast" in query.lower():
        tomorrow = datetime.utcnow() + timedelta(days=1)
        logger.info(f"Query is for forecast weather, using tomorrow: {tomorrow}")
        return tomorrow

    # Final fallback: try to parse any date in the string
    parsed = dateparser.parse(query, settings={"PREFER_DATES_FROM": "future"})
    logger.info(f"Fallback extracted date: {parsed}")
    return parsed


def extract_location_from_query(query):
    # Try to extract city/state/country after 'in', 'for', or 'at'
    match = re.search(
        r"(?:in|for|at)\s+([A-Za-z\s]+(?:,\s*[A-Za-z]{2,})*)", query, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    # Fallback: try to find a city name in the query
    match = re.search(r"([A-Za-z\s]+)(?:,\s*[A-Za-z]{2,})?", query)
    if match:
        return match.group(0).strip()
    return query.strip()


def _format_forecast_weather_data(data, city, date):
    entries = data.get("list", [])
    requested_date_str = date.strftime("%Y-%m-%d")
    filtered = [
        e for e in entries if e.get("dt_txt", "").startswith(requested_date_str)
    ]
    logger.info(
        f"Averaging {len(filtered)} forecast entries for {city} on {requested_date_str}"
    )
    if not filtered:
        return f"No forecast weather data available for {city} on {date.date()}."
    temps = [e["main"]["temp"] for e in filtered]
    humidities = [e["main"]["humidity"] for e in filtered]
    winds = [e["wind"]["speed"] for e in filtered]
    avg_temp = sum(temps) / len(temps)
    avg_humidity = sum(humidities) / len(humidities)
    avg_wind = sum(winds) / len(winds)
    avg_temp_f = (avg_temp * 9 / 5) + 32
    return (
        f"🔮 Forecast Weather for {city} ({date.strftime('%B %d, %Y')}):\n"
        f"- Avg Temperature: {avg_temp_f:.1f}°F ({avg_temp:.1f}°C)\n"
        f"- Avg Humidity: {avg_humidity:.0f}%\n"
        f"- Avg Wind: {avg_wind:.2f} m/s\n"
    )


def _get_city_id(city: str) -> Optional[str]:
    # Try to resolve city name to city ID using /weather endpoint
    city_variants = [city.strip()]
    if "," in city:
        city_variants.append(city.split(",")[0].strip())
    if not city.lower().endswith(",us"):
        city_variants.append(f"{city.strip()},US")
    if not city.lower().endswith(",usa"):
        city_variants.append(f"{city.strip()},USA")
    city_variants.append(city.strip().lower())
    city_variants = list(dict.fromkeys(city_variants))
    for city_variant in city_variants:
        params = {"q": city_variant, "appid": API_KEY, "units": "metric"}
        resp = requests.get(PRO_BASE_URL, params=params)
        if resp.status_code == 200:
            data = resp.json()
            city_id = str(data.get("id"))
            if city_id:
                return city_id
    return None


def _try_api_with_city_id(
    base_url, city, params, date=None, is_forecast=False, is_historical=False
):
    city_id = _get_city_id(city)
    if city_id:
        params["id"] = city_id
        params.pop("q", None)
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        logger.info(f"Final API URL: {url}")
        response = requests.get(base_url, params=params)
        logger.info(f"API response status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            logger.info(
                f"API response for city ID {city_id}: {json.dumps(data)[:200]}..."
            )
            if is_forecast:
                return _format_forecast_weather_data(data, city, date), None
            elif is_historical:
                return _format_historical_weather_data(data, city, date), None
            else:
                return _format_weather_data(data, city), None
        else:
            logger.warning(
                f"API error for city ID {city_id}: {response.status_code} - {response.text}"
            )
    # Fallback to q if city ID not found
    params["q"] = city
    params.pop("id", None)
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    logger.info(f"Fallback: Final API URL: {url}")
    response = requests.get(base_url, params=params)
    logger.info(f"API response status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        logger.info(f"API response for city name {city}: {json.dumps(data)[:200]}...")
        if is_forecast:
            return _format_forecast_weather_data(data, city, date), None
        elif is_historical:
            return _format_historical_weather_data(data, city, date), None
        else:
            return _format_weather_data(data, city), None
    else:
        logger.warning(
            f"API error for city name {city}: {response.status_code} - {response.text}"
        )
    return None, f"Weather data not found for {city} (tried city ID and name)"
