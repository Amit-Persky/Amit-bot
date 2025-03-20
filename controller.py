from fastapi import FastAPI, Request, BackgroundTasks
import logging
import json
from telegram_bot import TelegramBot
from weather import WeatherService
from euroleague import EuroleagueService
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
s3BucketName = config.get("s3BucketName")
projectId = config.get("dialogflowProjectId", "your-dialogflow-project-id")

# Function to detect intent using Dialogflow.
# If text is "/start", we use the "Welcome" event.
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

    # Build the structure expected by the handler:
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
dialogflowHandler = DialogflowHandler(telegramBot, weatherService, euroleagueService)
telegramVoiceChannel = TelegramVoiceChannel(telegramToken, s3BucketName)

app = FastAPI(
    title="Dialogflow Webhook with Telegram Integration",
    version="1.0.0",
    description="This API handles webhook requests from Telegram and integrates with Dialogflow."
)

@app.get("/")
def readRoot():
    return {"message": "Welcome to the Webhook API. Visit /docs for Swagger UI."}

@app.post("/amit-bot")
async def amitBotWebhook(request: Request, background_tasks: BackgroundTasks):
    try:
        logging.info("Received a new webhook request.")
        requestJson = await request.json()
        logging.info(f"Incoming JSON: {json.dumps(requestJson, indent=2)}")
        
        # Handle callback_query (button click)
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
            else:
                return {"status": "no content"}
        
        # If the request comes directly from Dialogflow (fulfillment)
        if "queryResult" in requestJson:
            logging.info("Processing Dialogflow webhook fulfillment request.")
            queryResult = requestJson.get("queryResult", {})
            # If the queryResult is empty or missing intent info, assume it's a duplicate voice processing call and ignore it.
            if not queryResult or not queryResult.get("intent", {}).get("displayName"):
                logging.info("Empty queryResult or missing intent detected. Ignoring duplicate fulfillment request.")
                return {"status": "ok"}
            responsePayload = dialogflowHandler.processRequest(requestJson)
            return responsePayload
        else:
            logging.info("Processing Telegram update.")
            message = requestJson.get("message", {})
            chat = message.get("chat", {})
            chatId = chat.get("id")
            
            # Process voice or audio messages in the background
            if "voice" in message or "audio" in message:
                logging.info("Detected voice message. Sending immediate acknowledgment.")
                initial_text = "We are processing your request, please wait..."
                telegramBot.sendMessage(chatId, initial_text)
                background_tasks.add_task(
                    telegramVoiceChannel.processWebhook, 
                    requestJson, dialogflowHandler, config, projectId
                )
                return {"status": "ok"}
            elif "text" in message:
                logging.info("Processing text message via detectIntent.")
                text = message.get("text", "")
                queryResult = detectIntent(projectId, str(chatId), text)
                logging.info("detectIntent result: %s", json.dumps(queryResult, indent=2))
                responsePayload = dialogflowHandler.processRequest({"queryResult": queryResult})
                
                # Attempt to extract reply_markup from fulfillmentMessages if available
                reply_markup = None
                fulfillmentMessages = responsePayload.get("fulfillmentMessages", [])
                for msg in fulfillmentMessages:
                    if "payload" in msg and "telegram" in msg["payload"]:
                        telegramPayload = msg["payload"]["telegram"]
                        reply_markup = telegramPayload.get("reply_markup")
                        break

                fulfillmentText = responsePayload.get("fulfillmentText", "I'm sorry, I didn't understand that request.")
                telegramBot.sendMessage(chatId, fulfillmentText, reply_markup=reply_markup)
                responsePayload = {"status": "ok"}
            else:
                logging.info("No text or voice in message.")
                responsePayload = {"status": "no content"}
            
            logging.info("Returning response payload: %s", json.dumps(responsePayload))
            return responsePayload
    except Exception as e:
        logging.exception("Error processing webhook")
        return {"error": str(e)}
