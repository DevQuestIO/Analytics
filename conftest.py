import pytest
import asyncio
import motor.motor_asyncio
from beanie import init_beanie
from models import UserProgress

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def mongodb():
    """Create a MongoDB test database."""
    client = motor.motor_asyncio.AsyncIOMotorClient(
        "mongodb://localhost:27017"
    )
    db = client.test_devquest
    
    # Initialize Beanie with the document models
    await init_beanie(
        database=db,
        document_models=[UserProgress]
    )
    
    yield db
    
    # Cleanup after all tests
    await db.user_progress.delete_many({})  # Changed from drop to delete_many
    client.close()

@pytest.fixture(autouse=True)
async def clean_db(mongodb):
    """Clean the UserProgress collection before each test."""
    await mongodb.user_progress.delete_many({})  # Changed from drop to delete_many
    await init_beanie(database=mongodb, document_models=[UserProgress])
    yield