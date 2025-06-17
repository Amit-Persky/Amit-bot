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

    def getIntentDisplayName(self, queryResult: dict) -> str:
        intentObj = queryResult.get("intent", {})
        return intentObj.get("displayName") or intentObj.get("display_name", "")

    def handleDefaultWelcome(self, queryResult: dict) -> dict:
        messages = queryResult.get("fulfillmentMessages", [])
        for msg in messages:
            if "payload" in msg:
                tgPayload = msg["payload"].get("telegram", {})
                text = tgPayload.get("text", "")
                return {"fulfillmentText": text, "fulfillmentMessages": [msg]}
        defaultMsg = "Hello and welcome!"
        logging.info("DefaultWelcomeIntent payload not found, using default message.")
        return {"fulfillmentText": defaultMsg, "fulfillmentMessages": [{"text": {"text": [defaultMsg]}}]}

    def handleUnhandledIntent(self, intentDisplayName: str) -> dict:
        defaultMsg = "I'm sorry, I didn't understand that request."
        logging.info(f"Unhandled intent: {intentDisplayName}.")
        return {"fulfillmentText": defaultMsg, "fulfillmentMessages": [{"text": {"text": [defaultMsg]}}]}

    def processRequest(self, requestJson: dict) -> dict:
        logging.info("Processing Dialogflow request.")
        queryResult = requestJson.get("queryResult", {})
        intentDisplayName = self.getIntentDisplayName(queryResult)
        if not intentDisplayName:
            logging.info("Empty queryResult or missing intent. Ignoring request.")
            return {"status": "ok"}
        parameters = queryResult.get("parameters", {})
        logging.info(f"Intent detected: {intentDisplayName}")
        logging.info(f"Parameters: {parameters}")
        if intentDisplayName == "GetEuroleague":
            return self.handleEuroleagueIntent(queryResult, parameters)
        elif intentDisplayName == "GetWeather":
            return self.handleWeatherIntent(queryResult, parameters)
        elif intentDisplayName == "GetPlaces":
            return self.handlePlacesIntent(queryResult, parameters)
        elif intentDisplayName == "DefaultWelcomeIntent":
            return self.handleDefaultWelcome(queryResult)
        else:
            return self.handleUnhandledIntent(intentDisplayName)

    # --- Helper functions for Euroleague intent ---
    def parseGameYear(self, gameYearRaw):
        if gameYearRaw:
            match = re.search(r'(20\d{2})', gameYearRaw)
            if match:
                return "E" + match.group(1)
            return "E2024"
        return "E2024"

    def handleEuroleagueDefault(self, teamName, gameYear, queryText, dateTime=None):
        lastSyn = ["last", "latest", "previous", "most recent", "past", "final"]
        nextSyn = ["next", "upcoming", "coming", "following", "future", "subsequent"]
        # If there is a request for the next game
        if any(s in queryText for s in nextSyn):
            result = self.euroleagueService.getNextGameFormatted(gameYear, teamName)
        # If there is a request for the last game, or dateTime is missing (or empty), return the last game by default
        elif any(s in queryText for s in lastSyn) or not dateTime:
            result = self.euroleagueService.getLastGameResult(gameYear, teamName)
        # If there is a dateTime, search for games by date
        elif dateTime:
            # Here you can add advanced logic for date filtering, currently returns all results (as before)
            result = self.euroleagueService.getSeasonResults(gameYear, teamName)
        else:
            result = self.euroleagueService.getSeasonResults(gameYear, teamName)
        logging.info("Returning Euroleague results.")
        return {"fulfillmentText": result, "fulfillmentMessages": [{"text": {"text": [result]}}]}

    def handleEuroleagueGameCode(self, teamName, gameYear, gameCode):
        try:
            codeInt = int(gameCode)
        except ValueError:
            codeInt = 0
        result = self.euroleagueService.getGameResults(gameYear, codeInt, teamName)
        logging.info("Returning Euroleague results for game code.")
        return {"fulfillmentText": result, "fulfillmentMessages": [{"text": {"text": [result]}}]}

    def handleEuroleagueGameNumber(self, teamName, gameYear, gameNumber):
        try:
            numInt = int(gameNumber)
        except ValueError:
            numInt = 0
        result = self.euroleagueService.getSchedules(gameYear, numInt, teamName)
        logging.info("Returning Euroleague schedules for game number.")
        return {"fulfillmentText": result, "fulfillmentMessages": [{"text": {"text": [result]}}]}

    def handleEuroleagueIntent(self, queryResult: dict, parameters: dict) -> dict:
        teamName = parameters.get("team")
        gameYearRaw = parameters.get("euroSeason")
        gameYear = self.parseGameYear(gameYearRaw)
        gameCode = parameters.get("gameCode")
        gameNumber = parameters.get("gameNumber")
        dateTime = parameters.get("date-time")
        queryText = queryResult.get("queryText", "").lower()

        # Enhancement: If euroSeason (gameYearRaw) contains 'next' or 'upcoming', treat as request for next game
        if teamName and gameYearRaw and any(x in gameYearRaw.lower() for x in ["next", "upcoming"]):
            result = self.euroleagueService.getNextGameFormatted(gameYear, teamName)
            return {"fulfillmentText": result, "fulfillmentMessages": [{"text": {"text": [result]}}]}

        if teamName and gameYear and not gameCode and not gameNumber:
            return self.handleEuroleagueDefault(teamName, gameYear, queryText, dateTime)
        elif teamName and gameYear and gameCode:
            return self.handleEuroleagueGameCode(teamName, gameYear, gameCode)
        elif teamName and gameYear and gameNumber:
            return self.handleEuroleagueGameNumber(teamName, gameYear, gameNumber)
        infoMsg = "Please provide game year and either game code or game number."
        logging.info(infoMsg)
        return {"fulfillmentText": infoMsg, "fulfillmentMessages": [{"text": {"text": [infoMsg]}}]}

    def handleWeatherIntent(self, queryResult: dict, parameters: dict) -> dict:
        geoCity = parameters.get("geo-city")
        forecastType = parameters.get("forecastPeriod", "")
        queryText = queryResult.get("queryText", "")
        if isinstance(forecastType, list):
            forecastType = " ".join(forecastType)
        logging.info(f"Extracted forecastType: {forecastType}")

        # --- Enhancement: Detect city-like words in queryText if geoCity is missing ---
        if not geoCity:
            import re
            # Try to extract a city name after 'in', 'at', or 'for' (e.g., 'weather in Hogwarts', 'weather at Wakanda', 'weather for Gotham')
            match = re.search(r'(?:in|at|for)\s+([A-Za-z\s]+)[?\.!]*$', queryText)
            possible_city = None
            if match:
                possible_city = match.group(1).strip()
            else:
                # If not found, try to extract the last word (excluding stopwords and punctuation) as a possible city
                words = re.findall(r'\b[A-Za-z]+\b', queryText)
                stopwords = set(['weather', 'what', 'is', 'the', 'will', 'be', 'like', 'forecast', 'in', 'at', 'for', 'on', 'of', 'tell', 'me', 'please', 'today', 'tomorrow'])
                filtered = [w for w in words if w.lower() not in stopwords]
                if filtered:
                    possible_city = filtered[-1]
            if possible_city:
                weatherInfo = f"Sorry, I couldn't find any city named {possible_city}. Please try another city."
                logging.info(f"City not found: {possible_city}")
            else:
                weatherInfo = "Please provide a city name for weather forecast."
                logging.info("No city provided.")
            return {"fulfillmentText": weatherInfo, "fulfillmentMessages": [{"text": {"text": [weatherInfo]}}]}

        # --- Enhancement: If forecastType is empty but queryText contains future words, pass them to weatherService ---
        import re
        future_keywords = ["tomorrow", "in \\d+ days", "in one day", "in two days", "in three days", "after tomorrow", "next week"]
        found_future = False
        for kw in future_keywords:
            if re.search(kw, queryText, re.IGNORECASE):
                forecastType = kw if "tomorrow" in kw else queryText
                found_future = True
                break
        weatherInfo = self.weatherService.getWeatherData(
            geoCity, forecastType, original_query=queryText
        )
        logging.info("Returning weather data.")
        return {"fulfillmentText": weatherInfo, "fulfillmentMessages": [{"text": {"text": [weatherInfo]}}]}

    def handlePlacesIntent(self, queryResult: dict, parameters: dict) -> dict:
        placeType = parameters.get("place-type")
        city = parameters.get("geo-city")
        if not placeType or not city:
            infoMsg = ("Please provide a city and place type, e.g., 'restaurants in Rome' or 'parks in Tel Aviv'.")
            logging.info(infoMsg)
            return {"fulfillmentText": infoMsg, "fulfillmentMessages": [{"text": {"text": [infoMsg]}}]}
        result = self.placesApiService.getPlaces(placeType, city)
        logging.info("Returning Places API results.")
        return {"fulfillmentText": result, "fulfillmentMessages": [{"text": {"text": [result]}}]}
