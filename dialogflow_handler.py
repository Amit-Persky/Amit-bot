import logging
import re

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

class DialogflowHandler:
    def __init__(self, telegramBot, weatherService, euroleagueService, placesApiService):
        self.telegramBot = telegramBot
        self.weatherService = weatherService
        self.euroleagueService = euroleagueService
        self.placesApiService = placesApiService
        logging.info("DialogflowHandler initialized.")

    def processRequest(self, requestJson: dict) -> dict:
        logging.info("Processing Dialogflow request.")
        queryResult = requestJson.get("queryResult", {})
        intentObj = queryResult.get("intent", {})
        # Try to retrieve the intent's display name from either key
        intentDisplayName = intentObj.get("displayName") or intentObj.get("display_name", "")
        
        # If intent name is empty, ignore this fulfillment request.
        if not intentDisplayName:
            logging.info("Empty queryResult or missing intent detected. Ignoring this fulfillment request.")
            return {"status": "ok"}

        parameters = queryResult.get("parameters", {})
        logging.info(f"Intent detected: {intentDisplayName}")
        logging.info(f"Parameters received: {parameters}")

        if intentDisplayName == "GetEuroleague":
            return self.handleEuroleagueIntent(queryResult, parameters)
        elif intentDisplayName == "GetWeather":
            return self.handleWeatherIntent(queryResult, parameters)
        elif intentDisplayName == "GetPlaces":
            return self.handlePlacesIntent(queryResult, parameters)
        elif intentDisplayName == "DefaultWelcomeIntent":
            # For the welcome intent, try to extract the Telegram payload
            fulfillmentMessages = queryResult.get("fulfillmentMessages", [])
            for msg in fulfillmentMessages:
                if "payload" in msg:
                    telegramPayload = msg["payload"].get("telegram", {})
                    text = telegramPayload.get("text", "")
                    return {
                        "fulfillmentText": text,
                        "fulfillmentMessages": [msg]
                    }
            defaultMsg = "Hello and welcome!"
            logging.info("DefaultWelcomeIntent payload not found, using default message.")
            return {
                "fulfillmentText": defaultMsg,
                "fulfillmentMessages": [{"text": {"text": [defaultMsg]}}]
            }
        else:
            defaultMsg = "I'm sorry, I didn't understand that request."
            logging.info(f"Unhandled intent: {intentDisplayName}. Returning default response.")
            return {
                "fulfillmentText": defaultMsg,
                "fulfillmentMessages": [{"text": {"text": [defaultMsg]}}]
            }

    def handleEuroleagueIntent(self, queryResult: dict, parameters: dict) -> dict:
        # Extract the "team" parameter from Dialogflow
        teamName = parameters.get("team")
        # Extract the game year from the "euroSeason" parameter
        gameYear = parameters.get("euroSeason")
        if gameYear:
            # Extract 4 digits starting with 20
            match = re.search(r'(20\d{2})', gameYear)
            if match:
                gameYear = "E" + match.group(1)
            else:
                gameYear = "E2024"  # default if extraction fails
        else:
            gameYear = "E2024"  # default

        gameCode = parameters.get("gameCode")
        gameNumber = parameters.get("gameNumber")
        # Extract the original queryText (not the parameter)
        queryText = queryResult.get("queryText", "").lower()

        # Synonyms for "last" and "next"
        last_synonyms = ["last", "latest", "previous", "most recent", "past", "final"]
        next_synonyms = ["next", "upcoming", "coming", "following", "future", "subsequent"]

        if teamName and gameYear and not gameCode and not gameNumber:
            if any(syn in queryText for syn in last_synonyms):
                result = self.euroleagueService.getLastGameResult(gameYear, teamName)
            elif any(syn in queryText for syn in next_synonyms):
                result = self.euroleagueService.getNextGameFormatted(gameYear, teamName)
            else:
                result = self.euroleagueService.getSeasonResults(gameYear, teamName)
            logging.info("Returning Euroleague game results.")
            return {
                "fulfillmentText": result,
                "fulfillmentMessages": [{"text": {"text": [result]}}]
            }
        elif teamName and gameYear and gameCode:
            try:
                gameCodeInt = int(gameCode)
            except ValueError:
                gameCodeInt = 0
            result = self.euroleagueService.getGameResults(gameYear, gameCodeInt, teamName)
            logging.info("Returning Euroleague game results.")
            return {
                "fulfillmentText": result,
                "fulfillmentMessages": [{"text": {"text": [result]}}]
            }
        elif teamName and gameYear and gameNumber:
            try:
                gameNumberInt = int(gameNumber)
            except ValueError:
                gameNumberInt = 0
            result = self.euroleagueService.getSchedules(gameYear, gameNumberInt, teamName)
            logging.info("Returning Euroleague schedules.")
            return {
                "fulfillmentText": result,
                "fulfillmentMessages": [{"text": {"text": [result]}}]
            }
        else:
            infoMsg = "Please provide the game year and either the game code or game number for the team."
            logging.info(infoMsg)
            return {
                "fulfillmentText": infoMsg,
                "fulfillmentMessages": [{"text": {"text": [infoMsg]}}]
            }

    def handleWeatherIntent(self, queryResult: dict, parameters: dict) -> dict:
        geoCity = parameters.get("geo-city")
        forecastType = parameters.get("forecastPeriod", "")
        if isinstance(forecastType, list):
            forecastType = " ".join(forecastType)
        logging.info(f"Extracted forecastType: {forecastType}")

        if geoCity:
            logging.info(f"Processing weather request for city: {geoCity}, forecastType: {forecastType}")
            weatherInfo = self.weatherService.getWeatherData(
                geoCity,
                forecastType,
                original_query=queryResult.get("queryText", "")
            )
            logging.info("Returning weather data.")
        else:
            weatherInfo = "Please provide a city name for a weather forecast."
            logging.info("No city provided for weather forecast.")

        return {
            "fulfillmentText": weatherInfo,
            "fulfillmentMessages": [{"text": {"text": [weatherInfo]}}]
        }
    
    def handlePlacesIntent(self, queryResult: dict, parameters: dict) -> dict:
        placeType = parameters.get("place-type")
        city = parameters.get("geo-city")

        if not placeType or not city:
            infoMsg = (
                "Please provide a city and a place type, like 'restaurants in Rome' "
                "or 'parks in Tel Aviv'."
            )
            logging.info(infoMsg)
            return {
                "fulfillmentText": infoMsg,
                "fulfillmentMessages": [{"text": {"text": [infoMsg]}}]
            }

        placesResult = self.placesApiService.GetPlaces(placeType, city)
        logging.info("Returning Places API results.")
        return {
            "fulfillmentText": placesResult,
            "fulfillmentMessages": [{"text": {"text": [placesResult]}}]
        }
