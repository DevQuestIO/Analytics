from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import os
from dotenv import load_dotenv
from models import UserProgress
import logging

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('devquest.log'),
        logging.StreamHandler()
    ]
)


async def init_db():
    logger = logging.getLogger('devquest.database')
    try:
        client = AsyncIOMotorClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
        db = client[os.getenv("DB_NAME")]
        logger.info(f"Connecting to MongoDB database: {os.getenv('DB_NAME')}")
        await init_beanie(database=db, document_models=[UserProgress])
        logger.info("Successfully initialized Beanie with MongoDB")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise
