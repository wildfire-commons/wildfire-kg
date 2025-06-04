"""
Weather tool using LangChain's tool decorator.
"""

import os
import logging
import requests
from datetime import datetime, timedelta, timezone
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
    #logger.info(f"Geocoding attempts: {attempts}")
    for attempt in attempts:
        params = {"q": attempt, "limit": 1, "appid": API_KEY}
        #logger.info(f"Geocoding location: {attempt}")
        resp = requests.get(GEOCODE_URL, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                #logger.info(f"Geocoding result: {data[0]}")
                return data[0]
            #else:
                #logger.warning(f"No geocoding result for {attempt}")
        #else:
            #logger.warning(
            #    f"Geocoding failed for {attempt}: {resp.status_code} - {resp.text}"
            #)
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
    - "historical weather for San Diego, CA yesterday" → historical weather endpoint
    - "forecast weather for San Diego, CA tomorrow" → forecast weather endpoint

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
    🌡️ Weather for San Diego, CA (ExtractedDate):
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
    📅 Historical Weather for San Diego, CA (ExtractedDate):
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
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        logger.info(f"DEBUG: Current UTC date: {today.strftime('%Y-%m-%d')}")

        date = extract_date_from_query(query)
        location = extract_location_from_query(query)
        if date == 'OUT_OF_RANGE':
            return (f"📅 Weather for {location} (requested: '{query}'):\n"
                    f"• Historical weather data is only available for the last 30 days. "
                    f"Please specify a date within this range (e.g., 'yesterday', 'last week', 'one month ago').")
        if date is None:
            # fallback for other unparseable queries
            return (f"📅 Weather for {location} (requested: '{query}'):\n"
                    f"• Could not extract a valid date from your query. Please specify a date within the last 30 days (historical) or next 5 days (forecast)." )
        # Block API call if date is more than 30 days ago
        if (today.date() - date.date()).days > 30:
            return (f"📅 Weather for {location} (requested: '{query}'):\n"
                    f"• Historical weather data is only available for the last 30 days. "
                    f"Please specify a date within this range (e.g., 'yesterday', 'last week', 'one month ago').")
        if date:
            logger.info(f"DEBUG: Requested date: {date.strftime('%Y-%m-%d')}")
            logger.info(f"DEBUG: Days from today: {(date.date() - today.date()).days}")
        
        today_date = today.date()
        is_historical = date and date.date() < today_date
        is_forecast = date and date.date() > today_date
        is_current = not date or date.date() == today_date
        
        logger.info(f"Query Analysis:")
        logger.info(f"- Date: {date}")
        logger.info(f"- Location: {location}")
        logger.info(f"- Type: {'Historical' if is_historical else 'Forecast' if is_forecast else 'Current'}")

        # Check forecast range BEFORE geocoding
        if is_forecast:
            max_forecast_date = today_date + timedelta(days=5)
            logger.info(f"DEBUG: Checking forecast range - Requested date: {date.date()}, Max forecast date: {max_forecast_date}")
            if date.date() > max_forecast_date:
                logger.info(f"DEBUG: Forecast date {date.date()} is out of range (max: {max_forecast_date})")
                return (
                    f"🔮 Forecast Weather for {location} ({date.strftime('%B %d, %Y')}):\n"
                    f"• Forecast data is only available up to {max_forecast_date.strftime('%B %d, %Y')}. "
                    f"Please specify a date within this range for detailed forecast."
                )

        # Geocode location ONCE
        geo = geocode_location(location)
        if not geo:
            return f"Could not resolve location '{location}'. Please check the city name."
        
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
        if not API_KEY:
            return "Weather API key is not set. Please set the WEATHER_API_KEY environment variable."
        data = _call_weather_api(PRO_BASE_URL, params, "current", city_label)
        if not data:
            return f"No current weather data available for {city_label}."
        return _format_weather_data(data, city_label, date)
    except Exception as e:
        logger.error(f"Error in weather query: {str(e)}", exc_info=True)
        return f"Weather information for {query} is unavailable. Error: {str(e)}"


def _format_weather_data(data: Dict[str, Any], requested_location: str, date: Optional[datetime] = None) -> str:
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
        date_str = f" ({date.strftime('%B %d, %Y')})" if date else ""
        response = (
            f"🌡️ Weather for {requested_location}{date_str}:\n"
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
    query_lower = query.lower()
    base_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    def log(msg):
        logger.info(f"WEATHERTOOL: {msg}")

    # Handle natural language keywords
    if "yesterday" in query_lower:
        date = base_today - timedelta(days=1)
        log(f"Extracted date for 'yesterday': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date
    if "today" in query_lower or "current" in query_lower:
        date = base_today
        log(f"Extracted date for 'today/current': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date
    if "tomorrow" in query_lower:
        date = base_today + timedelta(days=1)
        log(f"Extracted date for 'tomorrow': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date

    if "last week" in query_lower:
        date = base_today - timedelta(days=7)
        log(f"Extracted date for 'last week': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date
    if "next week" in query_lower:
        date = base_today + timedelta(days=7)
        log(f"Extracted date for 'next week': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date
    if "last month" in query_lower:
        year = base_today.year if base_today.month > 1 else base_today.year - 1
        month = base_today.month - 1 if base_today.month > 1 else 12
        log(f"Extracted date for 'last month': {year}-{month:02d}-01")
        log(f"Final extracted date: {year}-{month:02d}-01 for query: {query}")
        return base_today.replace(year=year, month=month, day=1)
    if "next month" in query_lower:
        year = base_today.year if base_today.month < 12 else base_today.year + 1
        month = base_today.month + 1 if base_today.month < 12 else 1
        log(f"Extracted date for 'next month': {year}-{month:02d}-01")
        log(f"Final extracted date: {year}-{month:02d}-01 for query: {query}")
        return base_today.replace(year=year, month=month, day=1)

    # Match '2 days ago', '7 days ago', etc.
    match = re.search(r"(\d+)\s*days?\s+ago", query_lower)
    if match:
        days = int(match.group(1))
        date = base_today - timedelta(days=days)
        log(f"Extracted date for '{days} days ago': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date

    # Match '7 days from now' or '7 days later'
    match = re.search(r"(\d+)\s*days?\s*(from now|later)", query_lower)
    if match:
        days = int(match.group(1))
        date = base_today + timedelta(days=days)
        log(f"Extracted date for '{days} days from now': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date

    # Match 'in 7 days' or 'for 7 days'
    match = re.search(r"(?:in|for)\s*(\d+)\s*days?", query_lower)
    if match:
        days = int(match.group(1))
        date = base_today + timedelta(days=days)
        log(f"Extracted date for '{days} days from now': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date

    match = re.search(r"([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s*\d{4})", query, re.IGNORECASE)
    if match:
        date_str = match.group(0).strip()
        date_str = re.sub(r'(\d+)(?:st|nd|rd|th)', r'\1', date_str)
        parsed = dateparser.parse(date_str)
        if parsed:
            log(f"Extracted date for explicit date '{date_str}': {parsed.strftime('%Y-%m-%d')}")
            log(f"Final extracted date: {parsed.strftime('%Y-%m-%d')} for query: {query}")
            return parsed.replace(hour=0, minute=0, second=0, microsecond=0)

    parsed = dateparser.parse(query)
    if parsed:
        log(f"Extracted date for fallback parse: {parsed.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {parsed.strftime('%Y-%m-%d')} for query: {query}")
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0)

    # Block 'years ago' and 'more than 1 month ago' (must be after all other checks)
    if re.search(r"\d+\s*year[s]?\s*ago", query_lower) or "one year ago" in query_lower:
        log("Year-based queries are not supported. Returning OUT_OF_RANGE.")
        return 'OUT_OF_RANGE'

    match = re.search(r'(\d+)\s*month[s]?\s*ago', query_lower)
    if match:
        months_ago = int(match.group(1))
        if months_ago > 1:
            log(f"Queries for more than one month ago ('{months_ago} months ago') are not supported. Returning OUT_OF_RANGE.")
            return 'OUT_OF_RANGE'
        # Allow '1 month ago' as 30 days
        date = base_today - timedelta(days=30)
        log(f"Extracted date for 'one month ago': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date
    if "one month ago" in query_lower:
        date = base_today - timedelta(days=30)
        log(f"Extracted date for 'one month ago': {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date

    # Only as a last resort
    if "historical" in query_lower:
        date = base_today - timedelta(days=1)
        log(f"Extracted date for 'historical' (default yesterday): {date.strftime('%Y-%m-%d')}")
        log(f"Final extracted date: {date.strftime('%Y-%m-%d')} for query: {query}")
        return date

    log(f"Final extracted date: None for query: {query}")
    log("No date extracted from query.")
    return None


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
    filtered = [e for e in entries if e.get("dt_txt", "").startswith(requested_date_str)]
    logger.info(f"WEATHERTOOL: {len(filtered)} forecast entries for {city} on {requested_date_str}")
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
                return _format_weather_data(data, city, date), None
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
            return _format_weather_data(data, city, date), None
    else:
        logger.warning(
            f"API error for city name {city}: {response.status_code} - {response.text}"
        )
    return None, f"Weather data not found for {city} (tried city ID and name)"
