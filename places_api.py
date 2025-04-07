import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

class PlacesApiService:
    def __init__(self, googleApiKey: str):
        self.apiKey = googleApiKey
        self.baseUrl = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        logging.info("PlacesApiService initialized.")

    def getPlaces(self, query: str, city: str, limit: int = 5) -> str:
        fullQuery = f"{query} in {city}"
        params = {
            "query": fullQuery,
            "key": self.apiKey
        }
        response = requests.get(self.baseUrl, params=params)
        if response.status_code != 200:
            logging.error("Places API request failed.")
            return "I'm sorry, I couldn't retrieve places at the moment."

        data = response.json()
        results = data.get('results', [])
        if not results:
            logging.info("No results found.")
            return (
                f"Sorry, I couldn't find any {query} in {city}.\n"
                f"Try a more common place type like 'restaurants', 'parks', or 'museums'."
            ) 

        responseLines = [f"Top {query} in {city}:\n"]
        for place in results[:limit]:
            name = place.get('name', 'Unnamed Place')
            address = place.get('formatted_address', 'No address')
            rating = place.get('rating', 'N/A')
            responseLines.append(f"{name} - {address} (Rating: {rating})")

        return "\n".join(responseLines)
