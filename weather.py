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
        """Main orchestrator for weather data retrieval and formatting."""
        coordinates = self.getCoordinates(city)
        if not coordinates:
            return "Sorry, I couldn't find the specified location."
        lat = coordinates.get("lat")
        lon = coordinates.get("lon")
        forecastWords = self.parseForecastWords(forecastType, original_query)
        if not forecastWords:
            return self.getDefaultCurrentWeather(city, lat, lon)
        forecastStr = self.getForecastTypeFromQuery(forecastWords, original_query)
        if "hourly" in forecastStr:
            return self.processHourlyForecast(city, lat, lon, original_query, forecastStr)
        result = self.processDailyForecast(city, lat, lon, forecastStr)
        if result:
            return result
        return "Sorry, I couldn't understand the forecast period. Please try 'tomorrow', 'hourly', 'in 3 days', etc."

    def parseForecastWords(self, forecastType, original_query):
        """Parse and normalize forecast type into a list of lower-case words."""
        if forecastType is None:
            return []
        if isinstance(forecastType, list):
            return [word.lower() for word in forecastType]
        return forecastType.strip().lower().split()

    def getDefaultCurrentWeather(self, city, lat, lon):
        """Return current weather if no forecast type is specified."""
        currentWeather = self.getCurrentWeather(lat, lon)
        if not currentWeather:
            return "Sorry, I couldn't retrieve current weather data for that location."
        temp = currentWeather.get("temp")
        weatherList = currentWeather.get("weather", [])
        description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
        dateStr = self.formatUnixTime(currentWeather.get("dt", 0))
        return (f"Current weather in {city} on {dateStr}:\n"
                f"Description: {description}\n"
                f"Temperature: {temp}°C")

    def getForecastTypeFromQuery(self, forecastWords, original_query):
        """Determine the forecast type string from forecast words and original query."""
        forecastWords = [word for word in forecastWords if word != "forecast"]
        forecastStr = " ".join(forecastWords)
        if not forecastStr:
            forecastStr = "hourly"
        if "hourly" in original_query.lower():
            forecastStr = "hourly"
        if "tomorrow" in original_query.lower() and "hourly" not in original_query.lower():
            forecastStr = "tomorrow"
        return forecastStr

    def processHourlyForecast(self, city, lat, lon, original_query, forecastStr):
        """Process and format hourly forecast, supporting up to 2 days ahead."""
        localHourlyMapping = {"tomorrow": 1, "1 days from now": 1, "2 days from now": 2}
        dayKey = None
        if re.search(r'\btomorrow\b', original_query.lower()):
            dayKey = "tomorrow"
        else:
            match = re.search(r'\b(\d+)\s*day', original_query.lower())
            if match:
                offset = int(match.group(1))
                if offset <= 2:
                    dayKey = f"{offset} days from now"
        if dayKey:
            hourlyData = self.getHourlyForecast(lat, lon)
            if not hourlyData:
                return "Sorry, I couldn't retrieve hourly forecast data."
            day_offset = localHourlyMapping.get(dayKey, 1)
            if day_offset > 2:
                return "Sorry, I couldn't retrieve hourly forecast data for that day."
            target_date = datetime.utcnow().date() + timedelta(days=day_offset)
            matching_hours = [f for f in hourlyData if datetime.utcfromtimestamp(f.get("dt", 0)).date() == target_date]
            if not matching_hours:
                return "Sorry, I couldn't retrieve hourly forecast data for that day."
            lines = []
            for forecast in matching_hours:
                forecast_time = datetime.utcfromtimestamp(forecast.get("dt", 0)).strftime('%H:%M')
                temp = forecast.get("temp")
                weatherList = forecast.get("weather", [])
                description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
                lines.append(f"{forecast_time} - {description}, {temp}°C")
            return f"Hourly forecast for {city} on {target_date}:\n" + "\n".join(lines)
        hourlyData = self.getHourlyForecast(lat, lon)
        if hourlyData and len(hourlyData) > 0:
            forecast = hourlyData[0]
            temp = forecast.get("temp")
            weatherList = forecast.get("weather", [])
            description = weatherList[0].get("description", "No description available") if weatherList else "No description available"
            timeStr = datetime.utcfromtimestamp(forecast.get("dt", 0)).strftime('%Y-%m-%d %H:%M')
            return (f"Hourly forecast for {city} at {timeStr}:\n"
                    f"Description: {description}\n"
                    f"Temperature: {temp}°C")
        return "Sorry, I couldn't retrieve hourly forecast data."

    def processDailyForecast(self, city, lat, lon, forecastStr):
        # Process and format daily forecast using a mapping of phrases to days ahead.
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
                return (f"Forecast for {city} on {dateStr} ({selectedDailyKey}):\n"
                        f"Description: {description}\n"
                        f"Daytime Temperature: {tempDay}°C")
        return None
