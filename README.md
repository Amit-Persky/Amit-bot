Euroleague Traveler Bot

Euroleague Traveler Bot is a Telegram chatbot built for basketball enthusiasts who travel or want local info at their fingertips. It combines sports updates, weather forecasts, and travel recommendations into one convenient bot. With this bot, users can quickly check the latest Euroleague basketball game results, get up‑to‑date weather information for cities worldwide, and even discover popular places like parks, cafes, or museums. The bot supports both text and voice interactions, making it a handy companion whether you’re typing or speaking your query.

Key Features

Euroleague Team Results – Retrieve game results for any Euroleague team. Ask for the last game’s score, the next upcoming game, or an entire season summary.

Weather Forecasts – Get current weather and detailed forecasts (today, tomorrow, or multi‑day) for cities around the world.

Places of Interest – Discover top‑rated restaurants, parks, museums, cafés, and other attractions in a chosen city.

Text & Voice Interaction – Send queries by typing or by recording a voice message. Voice requests are transcribed (AWS Transcribe) and answers can be returned as speech (AWS Polly).

AI & Cloud‑Powered – Google Dialogflow handles intent recognition, while AWS and external APIs deliver data in real time.

Architecture Overview



Voice messages follow a special path: Telegram → S3 → AWS Transcribe → Dialogflow → FastAPI → AWS Polly → Telegram.

Installation & Deployment

Prerequisites

Service

What you need

Telegram

A bot token from @BotFather

OpenWeatherMap

API key

Google Cloud

Dialogflow project ID + service‑account JSON key, Google Places API key

AWS

Access Key ID, Secret Key, region, and an S3 bucket for audio; Polly & Transcribe enabled

Docker

Docker Engine running on your server/PC

Configuration (config.json)

Create a file named config.json in the project root and fill in your own keys/passwords:

{
  "TELEGRAM_TOKEN": "<YOUR_TELEGRAM_TOKEN>",
  "OPENWEATHERMAP_API_KEY": "<YOUR_OPENWEATHERMAP_API_KEY>",
  "S3_BUCKET_NAME": "<YOUR_S3_BUCKET_NAME>",
  "S3_REGION": "<YOUR_S3_REGION>",
  "AWS_ACCESS_KEY_ID": "<YOUR_AWS_ACCESS_KEY_ID>",
  "AWS_SECRET_ACCESS_KEY": "<YOUR_AWS_SECRET_ACCESS_KEY>",
  "AWS_REGION": "<YOUR_AWS_REGION>",
  "DIALOGFLOW_PROJECT_ID": "<YOUR_DIALOGFLOW_PROJECT_ID>",
  "GOOGLE_PLACES_API_KEY": "<YOUR_GOOGLE_PLACES_API_KEY>"
}

Important: The bot will not run with the placeholder values. Replace every field with real credentials.

Build & Run with Docker

sudo service docker start

# Build the image
sudo docker build -t your_bot_image .

# Run the container (port 8000 exposed)
sudo docker run -d --name your_bot_container -p 8000:8000 your_bot_image

After the container starts, set your Telegram webhook (replace host + token):

curl "https://api.telegram.org/bot<YOUR_TELEGRAM_TOKEN>/setWebhook?url=https://<YOUR_DOMAIN_OR_IP>/bot-webhook"

The bot will now receive Telegram updates at /bot-webhook (defined in controller.py).

Usage Examples

Type

Example Query

What happens

Text

What is the weather in Paris tomorrow?

Returns tomorrow’s forecast for Paris

Text

Show me the latest results for Real Madrid.

Sends last Euroleague score involving Real Madrid

Voice

🎤 "Give me some nice parks in Madrid"

Bot transcribes audio, fetches parks via Google Places, and replies as an audio list

API Reference (Swagger)

When the server is running, open /docs in your browser (e.g. http://localhost:8000/docs). Swagger UI lets you explore:

GET /test/weather  – quick weather checks

GET /test/euroleague – Euroleague queries

GET /test/places – place recommendations

Running Tests

For quality assurance, the project includes a suite of unit tests (using Pytest) that cover the core functionalities: the weather service, Euroleague service, voice‑processing pipeline, and places‑API integration.All major features have corresponding tests to verify they work correctly and to prevent regressions.

To execute the tests locally:

pip install -r requirements.txt   # if not inside Docker
pytest



License & Author

This project is released as open‑source software – feel free to fork, modify, and deploy it.

Author: [your_name] (GitHub: [@your_github_username])

Credits

Euroleague API – Used for fetching live game results, schedules, and team information for Euroleague basketball games.
OpenWeatherMap API – Provides the weather data (current conditions and forecasts) for cities worldwide.
Google Places API – Used to find places of interest (parks, restaurants, museums, etc.) and their details in various cities.
Google Dialogflow – Powers the natural language understanding of user queries (intent detection for weather, results, places, etc.).
Amazon Web Services – AWS cloud services support the voice features: Amazon S3 for storing audio files, Amazon Transcribe for converting speech to text, and Amazon Polly for synthesizing text responses into speech.
Python & FastAPI – The bot’s backend is built with Python 3, using the FastAPI framework to handle web requests (Telegram webhooks and API calls).
Docker – The application is containerized with Docker, which makes it easy to deploy on servers (e.g., AWS EC2) or any environment that supports Docker.

