from fastapi import FastAPI, Request, BackgroundTasks, Query, Body
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import Union
import logging
import json
from telegram_bot import TelegramBot
from weather import WeatherService
from euroleague import EuroleagueService
from places_api import PlacesApiService
from dialogflow_handler import DialogflowHandler
from telegram_voice import TelegramVoiceChannel
from google.cloud import dialogflow_v2 as dialogflow
from google.protobuf.json_format import MessageToDict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# --- Pydantic Response Models ---
class WeatherResponse(BaseModel):
    city: str = Field(..., description="City name")
    forecast: str = Field(None, description="Forecast type")
    result: str = Field(..., description="Weather result data")

class EuroleagueResponse(BaseModel):
    team: str = Field(..., description="Team name")
    season: str = Field(..., description="Season code")
    query: str = Field(..., description="Query type")
    result: str = Field(..., description="Euroleague result")

class PlaceItem(BaseModel):
    name: str = Field(..., description="Place name")
    address: str = Field(..., description="Address")
    rating: str = Field(..., description="Rating")

class PlacesResponse(BaseModel):
    city: str = Field(..., description="City name")
    place_type: str = Field(..., description="Type of place")
    results: list[PlaceItem] = Field(..., description="List of places")

class SimpleResult(BaseModel):
    result: Union[str, dict]

def loadConfig() -> dict:
    with open("config.json", "r") as configFile:
        return json.load(configFile)

CONFIG = loadConfig()
TELEGRAM_TOKEN = CONFIG.get("TELEGRAM_TOKEN")
OPENWEATHERMAP_API_KEY = CONFIG.get("OPENWEATHERMAP_API_KEY")
GOOGLE_PLACES_API_KEY = CONFIG.get("GOOGLE_PLACES_API_KEY")
S3_BUCKET_NAME = CONFIG.get("S3_BUCKET_NAME")
PROJECT_ID = CONFIG.get("DIALOGFLOW_PROJECT_ID", "your-dialogflow-project-id")

TELEGRAM_BOT = TelegramBot(TELEGRAM_TOKEN)
WEATHER_SERVICE = WeatherService(OPENWEATHERMAP_API_KEY)
EUROLEAGUE_SERVICE = EuroleagueService()
PLACES_API_SERVICE = PlacesApiService(GOOGLE_PLACES_API_KEY)
DIALOGFLOW_HANDLER = DialogflowHandler(TELEGRAM_BOT, WEATHER_SERVICE, EUROLEAGUE_SERVICE, PLACES_API_SERVICE)
TELEGRAM_VOICE_CHANNEL = TelegramVoiceChannel(TELEGRAM_TOKEN, S3_BUCKET_NAME)

app = FastAPI(
    title="Euroleague Traveler Bot API",
    version="2.0.0",
    description=(
        "A world-class API for weather, Euroleague basketball results, and places recommendations.\n\n"
        "Handles Telegram and Dialogflow webhooks, and provides easy-to-use test endpoints for all core services.\n\n"
        "Built with FastAPI. Explore, test, and integrate!"
    ),
    docs_url="/docs",
    redoc_url="/redoc"
)

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")

def detectIntent(projectId, sessionId, text, languageCode='en'):
    sessionClient = dialogflow.SessionsClient()
    session = sessionClient.session_path(projectId, sessionId)
    if text.strip() == "/start":
        logging.info("Using event input 'Welcome' for /start command")
        eventInput = dialogflow.EventInput(name="Welcome", language_code=languageCode)
        queryInput = dialogflow.QueryInput(event=eventInput)
    else:
        textInput = dialogflow.TextInput(text=text, language_code=languageCode)
        queryInput = dialogflow.QueryInput(text=textInput)
    response = sessionClient.detect_intent(request={"session": session, "query_input": queryInput})
    response_dict = MessageToDict(response._pb, preserving_proto_field_name=True)
    query_result = response_dict.get("query_result", {})
    return {
        "intent": {"displayName": query_result.get("intent", {}).get("display_name", "")},
        "parameters": query_result.get("parameters", {}),
        "fulfillmentText": query_result.get("fulfillment_text", ""),
        "fulfillmentMessages": query_result.get("fulfillment_messages", [])
    }

def processCallbackQuery(requestJson: dict) -> dict:
    callback = requestJson["callback_query"]
    chatId = callback["message"]["chat"]["id"]
    data = callback.get("data", "")
    logging.info(f"Processing callback query with data: {data}")
    if data == "/weather":
        TELEGRAM_BOT.sendMessage(chatId, "Please provide the city name for weather details.")
    elif data == "/euroleague":
        TELEGRAM_BOT.sendMessage(chatId, "Please provide the team name for Euroleague details.")
    elif data == "/places":
        TELEGRAM_BOT.sendMessage(chatId, "Please provide the type of place and city for recommendations.")
    else:
        return {"status": "no content"}
    return {"status": "ok"}

def processDialogflowRequest(requestJson: dict) -> dict:
    logging.info("Processing Dialogflow webhook request.")
    queryResult = requestJson.get("queryResult", {})
    if not queryResult or not queryResult.get("intent", {}).get("display_name"):
        logging.info("Empty queryResult or missing intent. Ignoring request.")
        return {"status": "ok"}
    return DIALOGFLOW_HANDLER.processRequest(requestJson)

def processTelegramText(message: dict, chatId) -> dict:
    text = message.get("text", "")
    queryResult = detectIntent(PROJECT_ID, str(chatId), text)
    logging.info("detectIntent result: %s", json.dumps(queryResult, indent=2))
    responsePayload = DIALOGFLOW_HANDLER.processRequest({"queryResult": queryResult})
    replyMarkup = None
    for msg in responsePayload.get("fulfillmentMessages", []):
        if "payload" in msg and "telegram" in msg["payload"]:
            replyMarkup = msg["payload"]["telegram"].get("reply_markup")
            break
    fulfillmentText = responsePayload.get("fulfillmentText", "I'm sorry, I didn't understand that request.")
    TELEGRAM_BOT.sendMessage(chatId, fulfillmentText, reply_markup=replyMarkup)
    return {"status": "ok"}


# Example payload for /amit-bot endpoint (used in Swagger UI)
amit_bot_example = {
    "message": {
        "chat": {"id": 123456789},
        "text": "Hello, what is the weather in Tel Aviv?"
    }
}

@app.post(
    "/amit-bot",
    summary="Webhook for Telegram/ Dialogflow requests",
    description="Main endpoint for receiving Telegram updates and Dialogflow requests.",
    response_model=dict,
)
async def amitBotWebhook(
    payload: dict = Body(..., example=amit_bot_example),
    background_tasks: BackgroundTasks = None
):
    try:
        logging.info("Received a new webhook request.")
        requestJson = payload
        logging.info(f"Incoming JSON: {json.dumps(requestJson, indent=2)}")
        if "callback_query" in requestJson:
            return processCallbackQuery(requestJson)
        if "queryResult" in requestJson:
            return processDialogflowRequest(requestJson)
        message = requestJson.get("message", {})
        chat = message.get("chat", {})
        chatId = chat.get("id")
        if "voice" in message or "audio" in message:
            return handleVoiceMessage(message, chatId, requestJson, background_tasks)
        elif "text" in message:
            return handleTextMessage(message, chatId)
        logging.info("No text or voice in message.")
        return {"status": "no content"}
    except Exception as e:
        logging.exception("Error processing webhook")
        return {"error": str(e)}

def handleVoiceMessage(message: dict, chatId, requestJson, backgroundTasks):
    logging.info("Detected voice message. Sending acknowledgment.")
    TELEGRAM_BOT.sendMessage(chatId, "We are processing your request, please wait...")
    backgroundTasks.add_task(
        TELEGRAM_VOICE_CHANNEL.processWebhook,
        requestJson, DIALOGFLOW_HANDLER, CONFIG, PROJECT_ID
    )
    return {"status": "ok"}

def handleTextMessage(message: dict, chatId):
    return processTelegramText(message, chatId)

@app.get(
    "/test/weather",
    summary="Weather Service Test",
    description="Test the weather service for a given city and forecast type.",
    response_model=WeatherResponse,
    tags=["Weather"]
)
def testWeather(
    city: str = Query(..., description="City name for testing", example="Tel Aviv"),
    forecast: str = Query(None, description="Forecast type (e.g., hourly, tomorrow, in 3 days)", example="in 3 days")
):
    result = WEATHER_SERVICE.getWeatherData(city, forecast)
    return WeatherResponse(city=city, forecast=forecast, result=result)

@app.get(
    "/test/euroleague",
    summary="Euroleague Service Test",
    description="Test the Euroleague service for a given team, season, and query type (last/next/all games).",
    response_model=EuroleagueResponse,
    tags=["Euroleague"]
)
def testEuroleague(
    team: str = Query(..., description="Team name", example="Barcelona"),
    season: str = Query("E2024", description="Season code (default: E2024)", example="E2024"),
    query: str = Query("last", description="Query type: last/next/other", example="last")
):
    queryLower = query.lower()
    if queryLower in ["last", "latest", "previous", "past"]:
        result = EUROLEAGUE_SERVICE.getLastGameResult(season, team)
    elif queryLower in ["next", "upcoming", "following"]:
        result = EUROLEAGUE_SERVICE.getNextGameFormatted(season, team)
    else:
        result = EUROLEAGUE_SERVICE.getSeasonResults(season, team)
    return EuroleagueResponse(team=team, season=season, query=query, result=result)

@app.get(
    "/test/places",
    summary="Places Service Test",
    description="Test the places service for a given city and type of place. Returns a list of recommended places.",
    response_model=PlacesResponse,
    tags=["Places"]
)
def testPlaces(
    city: str = Query(..., description="City name for testing", example="Paris"),
    place_type: str = Query(..., description="Type of place (e.g., restaurants, parks, museums)", example="restaurants")
):
    places_result = PLACES_API_SERVICE.getPlaces(place_type, city)
    # Parse the string result into structured data for Swagger (best effort)
    items = []
    if isinstance(places_result, str):
        lines = places_result.split("\n")[1:]
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(" - ")
            if len(parts) == 2:
                name = parts[0].strip()
                rest = parts[1]
                addr, _, rating_part = rest.partition(" (Rating: ")
                rating = rating_part.replace(")", "").strip() if rating_part else "N/A"
                items.append(PlaceItem(name=name, address=addr.strip(), rating=rating))
    return PlacesResponse(city=city, place_type=place_type, results=items)
