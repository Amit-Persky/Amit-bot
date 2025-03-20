import requests
import logging
from datetime import datetime, timedelta
import re

# Configure logging.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

class WeatherService:
    def __init__(self, apiKey: str):
        self.apiKey = apiKey
        logging.info("WeatherService initialized with provided API key.")

    def getCoordinates(self, city: str) -> dict:
        logging.info(f"Getting coordinates for city: {city}")
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={self.apiKey}"
        response = requests.get(url)
        if response.status_code == 200 and response.json():
            logging.info(f"Coordinates for {city} retrieved successfully.")
            return response.json()[0]
        else:
            logging.error(f"Failed to get coordinates for {city}. Status Code: {response.status_code}")
            return None

    def getCurrentWeather(self, lat: float, lon: float) -> dict:
        logging.info(f"Getting current weather for lat: {lat}, lon: {lon}")
        url = (f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}"
               f"&exclude=minutely,hourly,daily,alerts&units=metric&appid={self.apiKey}")
        response = requests.get(url)
        if response.status_code == 200:
            logging.info("Current weather data retrieved successfully.")
            return response.json().get("current", {})
        else:
            logging.error(f"Failed to retrieve current weather. Status Code: {response.status_code}")
            return None

    def getHourlyForecast(self, lat: float, lon: float) -> list:
        logging.info(f"Getting hourly forecast for lat: {lat}, lon: {lon}")
        url = (f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}"
               f"&exclude=minutely,daily,current,alerts&units=metric&appid={self.apiKey}")
        response = requests.get(url)
        if response.status_code == 200:
            logging.info("Hourly forecast data retrieved successfully.")
            return response.json().get("hourly", [])
        else:
            logging.error(f"Failed to retrieve hourly forecast. Status Code: {response.status_code}")
            return None

    def getDailyForecast(self, lat: float, lon: float) -> list:
        logging.info(f"Getting daily forecast for lat: {lat}, lon: {lon}")
        url = (f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}"
               f"&exclude=minutely,hourly,current,alerts&units=metric&appid={self.apiKey}")
        response = requests.get(url)
        if response.status_code == 200:
            logging.info("Daily forecast data retrieved successfully.")
            return response.json().get("daily", [])
        else:
            logging.error(f"Failed to retrieve daily forecast. Status Code: {response.status_code}")
            return None

    def formatUnixTime(self, timestamp: int) -> str:
        return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')

    def getWeatherData(self, city: str, forecastType: str = None, original_query: str = "") -> str:
        logging.info(f"Processing weather data for city: {city} with forecast type: {forecastType}")
        coordinates = self.getCoordinates(city)
        if not coordinates:
            logging.error("No coordinates found.")
            return "Sorry, I couldn't find the specified location."

        lat = coordinates.get("lat")
        lon = coordinates.get("lon")

        # Normalize forecastType: convert to a list of lower case words.
        if forecastType is None:
            forecastWords = []
        elif isinstance(forecastType, list):
            forecastWords = [word.lower() for word in forecastType]
        else:
            forecastWords = forecastType.strip().lower().split()

        # If no forecast type is provided, check original_query.
        if not forecastWords:
            if original_query and "hourly" in original_query.lower():
                logging.info("No forecast type provided; defaulting to 'hourly' based on original query.")
                forecastWords = ["hourly"]
            elif original_query and "tomorrow" in original_query.lower():
                logging.info("No forecast type provided; defaulting to 'tomorrow' based on original query.")
                forecastWords = ["tomorrow"]
            else:
                currentWeather = self.getCurrentWeather(lat, lon)
                if not currentWeather:
                    logging.error("No current weather data available.")
                    return "Sorry, I couldn't retrieve current weather data for that location."
                temp = currentWeather.get("temp")
                weatherList = currentWeather.get("weather", [])
                description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
                dateStr = self.formatUnixTime(currentWeather.get("dt", 0))
                result = (f"Current weather in {city} on {dateStr}:\n"
                          f"Description: {description}\n"
                          f"Temperature: {temp}°C")
                logging.info("Returning current weather data as default.")
                return result

        # Convert forecastWords back to string for simple checks.
        forecastStr = " ".join(forecastWords)

        # Adjust ambiguous forecast types.
        if forecastStr == "forecast":
            if original_query and "tomorrow" in original_query.lower():
                logging.info("Received forecast type 'forecast' and original query contains 'tomorrow'; interpreting as 'tomorrow'.")
                forecastWords = ["tomorrow"]
            else:
                logging.info("Received forecast type 'forecast'; interpreting as 'hourly'.")
                forecastWords = ["hourly"]

        # Mapping for daily forecasts with synonyms (including numeric variants).
        dailyMapping = {
            "tomorrow": 1,
            "next day": 1,
            "after tomorrow": 1,
            "the following day": 1,
            "day after tomorrow": 2,
            "two days from now": 2,
            "2 days from now": 2,
            "in 2 days": 2,
            "in 3 days": 3,
            "in three days": 3,
            "three days from now": 3,
            "after three days": 3,
            "in 4 days": 4,
            "four days from now": 4,
            "in 5 days": 5,
            "five days from now": 5,
            "in 6 days": 6,
            "six days from now": 6,
            "in 7 days": 7,
            "seven days from now": 7,
        }

        # Logic for full hourly breakdown for a specific day.
        # Sort the dailyMapping keys by length (descending) to prefer longer expressions.
        sortedDailyKeys = sorted(dailyMapping.keys(), key=lambda x: len(x), reverse=True)
        dayKey = None
        for key in sortedDailyKeys:
            if key in forecastStr:
                dayKey = key
                break
        # If no key was found in forecastStr, also check the original query.
        if dayKey is None:
            for key in sortedDailyKeys:
                if key in original_query.lower():
                    dayKey = key
                    break
        # If still no dayKey, try to capture a numeric day offset from the original query.
        if dayKey is None:
            match = re.search(r'\b(\d+)\s*day', original_query.lower())
            if match:
                offset = int(match.group(1))
                if offset <= 2:  # Only allow if offset is within available 48-hour range.
                    dayKey = f"{offset} days from now"

        if dayKey is not None and (("hourly" in forecastWords) or ("hourly" in original_query.lower())) and not re.search(r"at\s*\d{1,2}:\d{2}", original_query.lower()):
            logging.info("User requested a full hourly forecast for a specific day.")
            hourlyData = self.getHourlyForecast(lat, lon)
            if not hourlyData:
                logging.error("Hourly forecast data not available.")
                return "Sorry, I couldn't retrieve hourly forecast data."
            day_offset = dailyMapping.get(dayKey, 1)
            if day_offset > 2:
                logging.error("Hourly forecast data is not available beyond 48 hours.")
                return "Sorry, I couldn't retrieve hourly forecast data for that day."
            target_date = datetime.utcnow().date() + timedelta(days=day_offset)
            matching_hours = [
                forecast for forecast in hourlyData
                if datetime.utcfromtimestamp(forecast.get("dt", 0)).date() == target_date
            ]
            if not matching_hours:
                logging.error("No hourly data found for the requested day.")
                return "Sorry, I couldn't retrieve hourly forecast data for that day."
            lines = []
            for forecast in matching_hours:
                forecast_time = datetime.utcfromtimestamp(forecast.get("dt", 0)).strftime('%H:%M')
                temp = forecast.get("temp")
                weatherList = forecast.get("weather", [])
                description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
                lines.append(f"{forecast_time} - {description}, {temp}°C")
            result = f"Hourly forecast for {city} on {target_date}:\n" + "\n".join(lines)
            logging.info("Returning full hourly forecast for the requested day.")
            return result

        # Handle hourly forecast if forecastWords contains only "hourly".
        if forecastWords == ["hourly"]:
            hourlyData = self.getHourlyForecast(lat, lon)
            if hourlyData and len(hourlyData) > 0:
                forecast = hourlyData[0]
                temp = forecast.get("temp")
                weatherList = forecast.get("weather", [])
                description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
                timeStr = datetime.utcfromtimestamp(forecast.get("dt", 0)).strftime('%Y-%m-%d %H:%M')
                result = (f"Hourly forecast for {city} at {timeStr}:\n"
                          f"Description: {description}\n"
                          f"Temperature: {temp}°C")
                logging.info("Returning hourly forecast data.")
                return result
            else:
                logging.error("Hourly forecast data not available.")
                return "Sorry, I couldn't retrieve hourly forecast data."

        # Handle daily forecast using the mapping.
        selectedDailyKey = None
        for key in dailyMapping.keys():
            if key in forecastStr:
                selectedDailyKey = key
                break
        if selectedDailyKey is not None:
            dailyData = self.getDailyForecast(lat, lon)
            if dailyData and len(dailyData) > dailyMapping[selectedDailyKey]:
                forecast = dailyData[dailyMapping[selectedDailyKey]]
                tempDay = forecast.get("temp", {}).get("day")
                weatherList = forecast.get("weather", [])
                description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
                dateStr = self.formatUnixTime(forecast.get("dt", 0))
                result = (f"Forecast for {city} on {dateStr} ({selectedDailyKey}):\n"
                          f"Description: {description}\n"
                          f"Daytime Temperature: {tempDay}°C")
                logging.info("Returning daily forecast data.")
                return result
            else:
                logging.error("Daily forecast data not available for the requested day index.")
                return "Sorry, I couldn't retrieve daily forecast data for that day."

        logging.error("Forecast type not understood.")
        return "Sorry, I couldn't understand the forecast period. Please try 'tomorrow', 'hourly', 'in 3 days', etc."
