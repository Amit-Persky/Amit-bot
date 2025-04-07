import requests
import logging
from datetime import datetime, timedelta
import re

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

class WeatherService:
    DAILY_MAPPING = {
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
        logging.error(f"Failed to retrieve daily forecast. Status Code: {response.status_code}")
        return None

    def formatUnixTime(self, timestamp: int) -> str:
        return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')

    def determineForecastWords(self, forecastType, original_query: str) -> list:
        if forecastType is None:
            if original_query and "hourly" in original_query.lower():
                logging.info("Defaulting forecast to hourly based on original query.")
                return ["hourly"]
            if original_query and "tomorrow" in original_query.lower():
                logging.info("Defaulting forecast to tomorrow based on original query.")
                return ["tomorrow"]
            return []
        if isinstance(forecastType, list):
            return [word.lower() for word in forecastType]
        return forecastType.strip().lower().split()

    def getCurrentWeatherResult(self, city: str, lat: float, lon: float) -> str:
        currentWeather = self.getCurrentWeather(lat, lon)
        if not currentWeather:
            logging.error("No current weather data available.")
            return "Sorry, I couldn't retrieve current weather data for that location."
        temp = currentWeather.get("temp")
        weatherList = currentWeather.get("weather", [])
        description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
        dateStr = self.formatUnixTime(currentWeather.get("dt", 0))
        logging.info("Returning current weather data as default.")
        return (f"Current weather in {city} on {dateStr}:\n"
                f"Description: {description}\nTemperature: {temp}°C")

    def extractDayKey(self, text: str) -> str:
        forecastStr = text.lower()
        for key in sorted(self.DAILY_MAPPING.keys(), key=lambda x: len(x), reverse=True):
            if key in forecastStr:
                return key
        match = re.search(r'\b(\d+)\s*day', forecastStr)
        if match:
            offset = int(match.group(1))
            if offset <= 2:
                return f"{offset} days from now"
        return None

    def getHourlyForecastForDay(self, city: str, lat: float, lon: float, dayKey: str) -> str:
        hourlyData = self.getHourlyForecast(lat, lon)
        if not hourlyData:
            logging.error("Hourly forecast data not available.")
            return "Sorry, I couldn't retrieve hourly forecast data."
        day_offset = self.DAILY_MAPPING.get(dayKey, 1)
        if day_offset > 2:
            logging.error("Hourly forecast data is not available beyond 48 hours.")
            return "Sorry, I couldn't retrieve hourly forecast data for that day."
        target_date = datetime.utcnow().date() + timedelta(days=day_offset)
        matching_hours = [f for f in hourlyData if datetime.utcfromtimestamp(f.get("dt", 0)).date() == target_date]
        if not matching_hours:
            logging.error("No hourly data found for the requested day.")
            return "Sorry, I couldn't retrieve hourly forecast data for that day."
        lines = []
        for forecast in matching_hours:
            forecastTime = datetime.utcfromtimestamp(forecast.get("dt", 0)).strftime('%H:%M')
            temp = forecast.get("temp")
            weatherList = forecast.get("weather", [])
            description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
            lines.append(f"{forecastTime} - {description}, {temp}°C")
        logging.info("Returning full hourly forecast for the requested day.")
        return f"Hourly forecast for {city} on {target_date}:\n" + "\n".join(lines)

    def getHourlyForecastSummary(self, city: str, lat: float, lon: float) -> str:
        hourlyData = self.getHourlyForecast(lat, lon)
        if hourlyData and len(hourlyData) > 0:
            forecast = hourlyData[0]
            temp = forecast.get("temp")
            weatherList = forecast.get("weather", [])
            description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
            timeStr = datetime.utcfromtimestamp(forecast.get("dt", 0)).strftime('%Y-%m-%d %H:%M')
            logging.info("Returning hourly forecast summary.")
            return (f"Hourly forecast for {city} at {timeStr}:\n"
                    f"Description: {description}\nTemperature: {temp}°C")
        logging.error("Hourly forecast data not available.")
        return "Sorry, I couldn't retrieve hourly forecast data."

    def extractDailyKey(self, original_query: str) -> str:
        forecastStr = original_query.lower()
        for key in sorted(self.DAILY_MAPPING.keys(), key=lambda x: len(x), reverse=True):
            if key in forecastStr:
                return key
        return None

    def getDailyForecastForDay(self, city: str, lat: float, lon: float, dailyKey: str) -> str:
        dailyData = self.getDailyForecast(lat, lon)
        if dailyData and len(dailyData) > self.DAILY_MAPPING.get(dailyKey, 1):
            forecast = dailyData[self.DAILY_MAPPING.get(dailyKey, 1)]
            tempDay = forecast.get("temp", {}).get("day")
            weatherList = forecast.get("weather", [])
            description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
            dateStr = self.formatUnixTime(forecast.get("dt", 0))
            logging.info("Returning daily forecast data.")
            return (f"Forecast for {city} on {dateStr} ({dailyKey}):\n"
                    f"Description: {description}\nDaytime Temperature: {tempDay}°C")
        logging.error("Daily forecast data not available for the requested day index.")
        return "Sorry, I couldn't retrieve daily forecast data for that day."

    def getWeatherData(self, city: str, forecastType: str = None, original_query: str = "") -> str:
        logging.info(f"Processing weather data for city: {city} with forecast type: {forecastType}")
        coordinates = self.getCoordinates(city)
        if not coordinates:
            logging.error("No coordinates found.")
            return "Sorry, I couldn't find the specified location."
        lat = coordinates.get("lat")
        lon = coordinates.get("lon")
        forecastWords = self.determineForecastWords(forecastType, original_query)
        if not forecastWords:
            return self.getCurrentWeatherResult(city, lat, lon)
        if "forecast" in forecastWords:
            if "tomorrow" in original_query.lower():
                forecastWords = ["tomorrow"]
            else:
                forecastWords = ["hourly"]
        if "hourly" in forecastWords:
            dayKey = self.extractDayKey(original_query)
            if dayKey and not re.search(r"at\s*\d{1,2}:\d{2}", original_query.lower()):
                return self.getHourlyForecastForDay(city, lat, lon, dayKey)
            else:
                return self.getHourlyForecastSummary(city, lat, lon)
        dailyKey = self.extractDailyKey(original_query)
        if dailyKey:
            return self.getDailyForecastForDay(city, lat, lon, dailyKey)
        logging.error("Forecast type not understood.")
        return "Sorry, I couldn't understand the forecast period. Please try 'tomorrow', 'hourly', 'in 3 days', etc."
