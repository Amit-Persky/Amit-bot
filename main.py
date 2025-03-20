import uvicorn
import logging
from controller import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

if __name__ == "__main__":
    logging.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
