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

    def normalizePlaceType(self, query: str) -> str:
        # Extracts the main place type from the query (e.g., "restaurants", "parks", etc.).
        import re
        place_keywords = [
            "restaurant", "restaurants", "park", "parks", "museum", "museums", "cafe", "cafes", "coffee shop", "coffee shops",
            "bar", "bars", "hotel", "hotels", "pub", "pubs", "attraction", "attractions", "mall", "malls"
        ]
        query_lower = query.lower()
        for word in place_keywords:
            if word in query_lower:
                return word
        # fallback: extract last word
        words = re.findall(r"\w+", query_lower)
        return words[-1] if words else query_lower.strip()

    def getPlaces(self, query: str, city: str, limit: int = 5) -> str:
        if not query or not city:
            return "Please specify both the type of place and the city."
        place_type = self.normalizePlaceType(query)
        fullQuery = f"{place_type} in {city}"
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
            return (
                f"Sorry, I couldn't find any {place_type} in {city}.\n"
                f"Try a more common place type like 'restaurants', 'parks', or 'museums'."
            )

        # Improved user-facing message
        if place_type.endswith('s'):
            responseLines = [f"Here are some recommended {place_type} in {city}:"]
        else:
            responseLines = [f"Here are some recommended {place_type}s in {city}:"]
        for place in results[:limit]:
            name = place.get('name', 'Unnamed Place')
            address = place.get('formatted_address', 'No address')
            rating = place.get('rating', 'N/A')
            responseLines.append(f"{name} - {address} (Rating: {rating})")

        return "\n".join(responseLines)
