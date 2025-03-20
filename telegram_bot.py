import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.baseUrl = f"https://api.telegram.org/bot{token}"
        logging.info("TelegramBot initialized.")

    def sendMessage(self, chatId: int, text: str, reply_markup=None) -> dict:
        logging.info(f"Sending message to chat_id {chatId}")
        url = f"{self.baseUrl}/sendMessage"
        payload = {"chat_id": chatId, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = requests.post(url, json=payload)
        logging.info("Message sent.")
        return response.json()
