from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.openapi.docs import get_swagger_ui_html
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

def loadConfig() -> dict:
    with open("config.json", "r") as configFile:
        return json.load(configFile)

config = loadConfig()
TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN")
OPENWEATHERMAP_API_KEY = config.get("OPENWEATHERMAP_API_KEY")
GOOGLE_PLACES_API_KEY = config.get("GOOGLE_PLACES_API_KEY")
S3_BUCKET_NAME = config.get("S3_BUCKET_NAME")
PROJECT_ID = config.get("DIALOGFLOW_PROJECT_ID", "your-dialogflow-project-id")

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

telegramBot = TelegramBot(TELEGRAM_TOKEN)
weatherService = WeatherService(OPENWEATHERMAP_API_KEY)
euroleagueService = EuroleagueService()
placesApiService = PlacesApiService(GOOGLE_PLACES_API_KEY)
dialogflowHandler = DialogflowHandler(telegramBot, weatherService, euroleagueService, placesApiService)
telegramVoiceChannel = TelegramVoiceChannel(TELEGRAM_TOKEN, S3_BUCKET_NAME)

app = FastAPI(
    title="Dialogflow Webhook with Telegram Integration",
    version="1.1.0",
    description=(
        "API for handling Webhook requests from Telegram and integrating with Dialogflow.\n\n"
        "This tool works with 3 intents: GetEuroleague, GetWeather, and GetPlaces.\n\n"
        "Additionally, you can test the Weather, Euroleague and Places services via dedicated endpoints with JSON examples."
    )
)

@app.get("/docs", include_in_schema=False)
async def customSwaggerUiHtml():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        swagger_js_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.15.5/swagger-ui-bundle.js",
        swagger_css_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.15.5/swagger-ui.css",
    )

@app.get("/", summary="Welcome", description="Home screen with a basic message. Visit /docs for Swagger UI.")
def readRoot():
    return {"message": "Welcome to the Webhook API. Visit /docs for Swagger UI."}

def processCallbackQuery(requestJson: dict) -> dict:
    callback = requestJson["callback_query"]
    chatId = callback["message"]["chat"]["id"]
    data = callback.get("data", "")
    logging.info(f"Processing callback query with data: {data}")
    if data == "/weather":
        telegramBot.sendMessage(chatId, "Please provide the city name so I can fetch the weather details.")
    elif data == "/euroleague":
        telegramBot.sendMessage(chatId, "Please provide the team name for Euroleague details.")
    elif data == "/places":
        telegramBot.sendMessage(chatId, "Please provide the type of place and city for recommendations.")
    else:
        return {"status": "no content"}
    return {"status": "ok"}

def processDialogflowRequest(requestJson: dict) -> dict:
    logging.info("Processing Dialogflow webhook fulfillment request.")
    queryResult = requestJson.get("queryResult", {})
    if not queryResult or not queryResult.get("intent", {}).get("display_name"):
        logging.info("Empty queryResult or missing intent detected. Ignoring duplicate fulfillment request.")
        return {"status": "ok"}
    return dialogflowHandler.processRequest(requestJson)

def processTelegramText(message: dict, chatId) -> dict:
    text = message.get("text", "")
    queryResult = detectIntent(PROJECT_ID, str(chatId), text)
    logging.info("detectIntent result: %s", json.dumps(queryResult, indent=2))
    responsePayload = dialogflowHandler.processRequest({"queryResult": queryResult})
    reply_markup = None
    for msg in responsePayload.get("fulfillmentMessages", []):
        if "payload" in msg and "telegram" in msg["payload"]:
            telegramPayload = msg["payload"]["telegram"]
            reply_markup = telegramPayload.get("reply_markup")
            break
    fulfillmentText = responsePayload.get("fulfillmentText", "I'm sorry, I didn't understand that request.")
    telegramBot.sendMessage(chatId, fulfillmentText, reply_markup=reply_markup)
    return {"status": "ok"}

@app.post("/amit-bot", summary="Webhook for Telegram/ Dialogflow requests", description="Main endpoint for receiving Telegram updates and Dialogflow requests.")
async def amitBotWebhook(request: Request, background_tasks: BackgroundTasks):
    try:
        logging.info("Received a new webhook request.")
        requestJson = await request.json()
        logging.info(f"Incoming JSON: {json.dumps(requestJson, indent=2)}")
        if "callback_query" in requestJson:
            return processCallbackQuery(requestJson)
        if "queryResult" in requestJson:
            return processDialogflowRequest(requestJson)
        message = requestJson.get("message", {})
        chat = message.get("chat", {})
        chatId = chat.get("id")
        if "voice" in message or "audio" in message:
            logging.info("Detected voice message. Sending immediate acknowledgment.")
            telegramBot.sendMessage(chatId, "We are processing your request, please wait...")
            background_tasks.add_task(
                telegramVoiceChannel.processWebhook, 
                requestJson, dialogflowHandler, config, PROJECT_ID
            )
            return {"status": "ok"}
        elif "text" in message:
            return processTelegramText(message, chatId)
        else:
            logging.info("No text or voice in message.")
            return {"status": "no content"}
    except Exception as e:
        logging.exception("Error processing webhook")
        return {"error": str(e)}

@app.get("/test/weather", summary="Weather Service Test", response_model=dict)
def testWeather(
    city: str = Query(..., description="City name for testing", example="Tel Aviv"),
    forecast: str = Query(None, description="Forecast type (e.g., hourly, tomorrow, in 3 days)", example="hourly")
):
    result = weatherService.getWeatherData(city, forecast)
    return {"result": result}

@app.get("/test/euroleague", summary="Euroleague Service Test", response_model=dict)
def testEuroleague(
    team: str = Query(..., description="Team name", example="Barcelona"),
    season: str = Query("E2024", description="Season code (default: E2024)", example="E2024"),
    query: str = Query("last", description="Query type: last/next/other", example="last")
):
    query_lower = query.lower()
    if query_lower in ["last", "latest", "previous", "past"]:
        result = euroleagueService.getLastGameResult(season, team)
    elif query_lower in ["next", "upcoming", "following"]:
        result = euroleagueService.getNextGameFormatted(season, team)
    else:
        result = euroleagueService.getSeasonResults(season, team)
    return {"result": result}

@app.get("/test/places", summary="Places Service Test", response_model=dict)
def testPlaces(
    city: str = Query(..., description="City name for testing", example="Paris"),
    place_type: str = Query(..., description="Type of place (e.g., restaurants, parks, museums)", example="restaurants")
):
    result = placesApiService.getPlaces(place_type, city)
    return {"result": result}
