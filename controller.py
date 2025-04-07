from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel
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

# Load configuration
config = loadConfig()
telegramToken = config.get("telegramToken")
openWeatherMapApiKey = config.get("openWeatherMapApiKey")
googlePlacesApiKey = config.get("googlePlacesApiKey")
s3BucketName = config.get("s3BucketName")
projectId = config.get("dialogflowProjectId", "your-dialogflow-project-id")

def detectIntent(projectId, sessionId, text, languageCode='en'):
    """
    Detects the intent via Dialogflow.
    If the text is exactly '/start', uses an event 'Welcome' to trigger the DefaultWelcomeIntent.
    Otherwise sends the text as a regular query.
    """
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
        "intent": {
            "displayName": query_result.get("intent", {}).get("display_name", "")
        },
        "parameters": query_result.get("parameters", {}),
        "fulfillmentText": query_result.get("fulfillment_text", ""),
        "fulfillmentMessages": query_result.get("fulfillment_messages", [])
    }

# Initialize services
telegramBot = TelegramBot(telegramToken)
weatherService = WeatherService(openWeatherMapApiKey)
euroleagueService = EuroleagueService()
placesApiService = PlacesApiService(googlePlacesApiKey)
dialogflowHandler = DialogflowHandler(telegramBot, weatherService, euroleagueService, placesApiService)
telegramVoiceChannel = TelegramVoiceChannel(telegramToken, s3BucketName)

app = FastAPI(
    title="Dialogflow Webhook with Telegram Integration",
    version="1.1.0",
    description=(
        "API for handling Webhook requests from Telegram and integrating with Dialogflow.\n\n"
        "This tool works with 3 intents: GetEuroleague, GetWeather, and GetPlaces.\n\n"
        "Additionally, you can test the Weather, Euroleague and Places services via dedicated endpoints with JSON examples."
    )
)

# Custom Swagger UI endpoint with the full (non-minimalistic) design using CDN assets
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        swagger_js_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.15.5/swagger-ui-bundle.js",
        swagger_css_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.15.5/swagger-ui.css",
    )

@app.get(
    "/",
    summary="Welcome",
    description="Home screen with a basic message. Visit /docs to view the Swagger UI."
)
def readRoot():
    return {"message": "Welcome to the Webhook API. Visit /docs for Swagger UI."}

@app.post(
    "/amit-bot",
    summary="Webhook for Telegram/ Dialogflow requests",
    description="Main endpoint for receiving Telegram updates and Dialogflow requests."
)
async def amitBotWebhook(request: Request, background_tasks: BackgroundTasks):
    try:
        logging.info("Received a new webhook request.")
        requestJson = await request.json()
        logging.info(f"Incoming JSON: {json.dumps(requestJson, indent=2)}")
        
        # Handling callback_query (button presses)
        if "callback_query" in requestJson:
            callback = requestJson["callback_query"]
            chatId = callback["message"]["chat"]["id"]
            data = callback.get("data", "")
            logging.info(f"Processing callback query with data: {data}")
            
            if data == "/weather":
                fulfillmentText = "Please provide the city name so I can fetch the weather details."
                telegramBot.sendMessage(chatId, fulfillmentText)
                return {"status": "ok"}
            elif data == "/euroleague":
                fulfillmentText = "Please provide the team name for Euroleague details."
                telegramBot.sendMessage(chatId, fulfillmentText)
                return {"status": "ok"}
            elif data == "/places":
                fulfillmentText = "Please provide the type of place and city for recommendations."
                telegramBot.sendMessage(chatId, fulfillmentText)
                return {"status": "ok"}
            else:
                return {"status": "no content"}
        
        # Handling requests coming from Dialogflow
        if "queryResult" in requestJson:
            logging.info("Processing Dialogflow webhook fulfillment request.")
            queryResult = requestJson.get("queryResult", {})
            if not queryResult or not queryResult.get("intent", {}).get("display_name"):
                logging.info("Empty queryResult or missing intent detected. Ignoring duplicate fulfillment request.")
                return {"status": "ok"}
            responsePayload = dialogflowHandler.processRequest(requestJson)
            return responsePayload
        
        else:
            logging.info("Processing Telegram update.")
            message = requestJson.get("message", {})
            chat = message.get("chat", {})
            chatId = chat.get("id")
            
            # Handle voice or audio messages
            if "voice" in message or "audio" in message:
                logging.info("Detected voice message. Sending immediate acknowledgment.")
                initial_text = "We are processing your request, please wait..."
                telegramBot.sendMessage(chatId, initial_text)
                background_tasks.add_task(
                    telegramVoiceChannel.processWebhook, 
                    requestJson, dialogflowHandler, config, projectId
                )
                return {"status": "ok"}
            
            # Handle text messages
            elif "text" in message:
                logging.info("Processing text message via detectIntent.")
                text = message.get("text", "")
                
                # No special patch for "/start places" needed 
                # because we'll handle everything via callback_data = "/places"

                queryResult = detectIntent(projectId, str(chatId), text)
                logging.info("detectIntent result: %s", json.dumps(queryResult, indent=2))
                responsePayload = dialogflowHandler.processRequest({"queryResult": queryResult})
                
                # Check if there's a telegram payload with inline keyboard
                reply_markup = None
                for msg in responsePayload.get("fulfillmentMessages", []):
                    if "payload" in msg and "telegram" in msg["payload"]:
                        telegramPayload = msg["payload"]["telegram"]
                        reply_markup = telegramPayload.get("reply_markup")
                        break
                
                fulfillmentText = responsePayload.get("fulfillmentText", "I'm sorry, I didn't understand that request.")
                telegramBot.sendMessage(chatId, fulfillmentText, reply_markup=reply_markup)
                return {"status": "ok"}
            
            else:
                logging.info("No text or voice in message.")
                return {"status": "no content"}
    
    except Exception as e:
        logging.exception("Error processing webhook")
        return {"error": str(e)}

# ------------------------------------------
# New endpoints with JSON examples for testing via Swagger
# ------------------------------------------

@app.get(
    "/test/weather",
    summary="Weather Service Test",
    response_model=dict,
    responses={
        200: {
            "description": "Example response",
            "content": {
                "application/json": {
                    "example": {
                        "result": "Current weather in Tel Aviv on 2025-03-20:\nDescription: clear sky\nTemperature: 25°C"
                    }
                }
            },
        }
    },
)
def test_weather(
    city: str = Query(..., description="City name for testing", example="Tel Aviv"),
    forecast: str = Query(None, description="Forecast type (e.g., hourly, tomorrow, in 3 days)", example="hourly")
):
    """
    This endpoint tests the weather service.
    
    You must provide the city name and optionally the forecast type.
    
    **Example request:**
    
    GET /test/weather?city=Tel%20Aviv&forecast=hourly
    
    **Example response:**
    
    {
      "result": "Current weather in Tel Aviv on 2025-03-20:\nDescription: clear sky\nTemperature: 25°C"
    }
    """
    result = weatherService.getWeatherData(city, forecast)
    return {"result": result}

@app.get(
    "/test/euroleague",
    summary="Euroleague Service Test",
    response_model=dict,
    responses={
        200: {
            "description": "Example response",
            "content": {
                "application/json": {
                    "example": {
                        "result": "Last game for Barcelona on Mar 15, 2025:\nBarcelona 89 - 85 Real Madrid"
                    }
                }
            },
        }
    },
)
def test_euroleague(
    team: str = Query(..., description="Team name", example="Barcelona"),
    season: str = Query("E2024", description="Season code (default: E2024)", example="E2024"),
    query: str = Query("last", description="Query type: last/next/other", example="last")
):
    """
    This endpoint tests the Euroleague service.
    
    You must provide the team name, season code (if applicable), and the query type.
    
    **Example request:**
    
    GET /test/euroleague?team=Barcelona&season=E2024&query=last
    
    **Example response:**
    
    {
      "result": "Last game for Barcelona on Mar 15, 2025:\nBarcelona 89 - 85 Real Madrid"
    }
    """
    query_lower = query.lower()
    if query_lower in ["last", "latest", "previous", "past"]:
        result = euroleagueService.getLastGameResult(season, team)
    elif query_lower in ["next", "upcoming", "following"]:
        result = euroleagueService.getNextGameFormatted(season, team)
    else:
        result = euroleagueService.getSeasonResults(season, team)
    return {"result": result}

@app.get(
    "/test/places",
    summary="Places Service Test",
    response_model=dict,
    responses={
        200: {
            "description": "Example response",
            "content": {
                "application/json": {
                    "example": {
                        "result": "Top restaurants in Paris: Le Meurice, L'Avenue, and Septime."
                    }
                }
            },
        }
    },
)
def test_places(
    city: str = Query(..., description="City name for testing", example="Paris"),
    place_type: str = Query(..., description="Type of place (e.g., restaurants, parks, museums)", example="restaurants")
):
    """
    This endpoint tests the Places service.
    
    You must provide the city name and the type of place.
    
    **Example request:**
    
    GET /test/places?city=Paris&place_type=restaurants
    
    **Example response:**
    
    {
      "result": "Top restaurants in Paris: Le Meurice, L'Avenue, and Septime."
    }
    """
    result = placesApiService.GetPlaces(place_type, city)
    return {"result": result}
