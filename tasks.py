import asyncio
# import nest_asyncio
from celery import Celery
from celery.signals import worker_process_init
from datetime import datetime, timedelta
import os
from typing import List
from models import UserProgress, Question
import logging
from leetcode_service import AnalyticsService
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('devquest.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('devquest.tasks')

# Initialize Celery with explicit Redis URL
# REDIS_URL = "redis://localhost:6379/0"
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DB_NAME = os.getenv('DB_NAME')
celery_app = Celery('analytics_tasks')

# Celery Configuration
celery_app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True,
    task_time_limit=30 * 60,
    worker_prefetch_multiplier=1,  # Process one task at a time
    task_routes={
        'tasks.sync_user_leetcode_data': {'queue': 'sync'},
        'tasks.update_user_statistics': {'queue': 'stats'},
        'tasks.periodic_sync_all_users': {'queue': 'periodic'},
    }
)

async def init_mongodb():
    """Initialize MongoDB connection"""
    client = AsyncIOMotorClient(MONGODB_URI)
    await init_beanie(database=client[DB_NAME], document_models=[UserProgress])
    return client

def setup_and_run_async(coro):
    """Setup event loop, MongoDB, and run coroutine"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def wrapper():
        # Initialize MongoDB connection
        client = await init_mongodb()
        try:
            return await coro
        finally:
            client.close()
    
    try:
        return loop.run_until_complete(wrapper())
    finally:
        loop.close()
        asyncio.set_event_loop(None)



@celery_app.task(bind=True, name='tasks.sync_user_leetcode_data')
def sync_user_leetcode_data(self, user_id: str, csrf_token: str, cookie: str, username: str):
    """Sync task for user's LeetCode data"""
    logger.info(f"Starting sync task for user {user_id} with task_id: {self.request.id}")
    try:
        async def execute_sync():
            try:
                analytics_service = AnalyticsService()
                logger.info(f"Starting sync_user_submissions for user {user_id}")
                result = await analytics_service.sync_user_submissions(
                    user_id=user_id,
                    csrf_token=csrf_token,
                    cookie=cookie,
                    username=username
                )
                logger.info(f"Completed sync_user_submissions for user {user_id}")
                return result
            except Exception as e:
                logger.error(f"Error in sync execution: {str(e)}", exc_info=True)
                raise

        # Execute the sync
        result = setup_and_run_async(execute_sync())
        logger.info(f"Successfully completed sync for user {user_id}")
        # Queue the stats update
        # update_user_statistics.delay(user_id)
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        logger.error(f"Failed to sync user {user_id} data: {str(e)}", exc_info=True)
        raise

# @celery_app.task(bind=True, name='tasks.update_user_statistics')
# def update_user_statistics(self, user_id: str):
#     """Update user statistics task"""
#     logger.info(f"Starting statistics update for user {user_id} with task_id: {self.request.id}")
    
#     async def execute_stats_update():
#         try:
#             user_progress = await UserProgress.find_one({"user_id": user_id})
#             if not user_progress:
#                 logger.warning(f"No progress found for user {user_id}")
#                 return {
#                     "status": "no_data",
#                     "message": f"No progress found for user {user_id}"
#                 }

#             leetcode_questions = (
#                 user_progress.progress_data.leetcode.questions 
#                 if user_progress.progress_data.leetcode 
#                 else []
#             )
            
#             # Calculate statistics
#             difficulty_counts = {"easy": 0, "medium": 0, "hard": 0}
#             topic_counts = {}
#             total_solved = 0
#             total_attempts = 0
            
#             for question in leetcode_questions:
#                 total_attempts += question.attempts
                
#                 if question.status == "solved":
#                     total_solved += 1
#                     difficulty_counts[question.difficulty.lower()] += 1
                    
#                     for topic in question.topics:
#                         topic_counts[topic] = topic_counts.get(topic, 0) + 1

#             # Update user progress
#             user_progress.aggregated_stats.total_solved = total_solved
#             user_progress.aggregated_stats.by_difficulty = difficulty_counts
#             user_progress.aggregated_stats.by_topic = topic_counts
#             user_progress.aggregated_stats.success_rate = (
#                 total_solved / total_attempts if total_attempts > 0 else 0
#             )
            
#             await user_progress.save()
            
#             stats_summary = {
#                 "total_solved": total_solved,
#                 "total_attempts": total_attempts,
#                 "success_rate": user_progress.aggregated_stats.success_rate,
#                 "by_difficulty": difficulty_counts,
#                 "by_topic": topic_counts
#             }
            
#             logger.info(f"Successfully updated statistics for user {user_id}: {stats_summary}")
#             return stats_summary
            
#         except Exception as e:
#             logger.error(f"Error in stats update: {str(e)}", exc_info=True)
#             raise

#     try:
#         # Run the async function with proper MongoDB initialization
#         result = setup_and_run_async(execute_stats_update())
#         return {
#             "status": "success",
#             "user_id": user_id,
#             "statistics": result
#         }
#     except Exception as e:
#         logger.error(f"Failed to update statistics for user {user_id}: {str(e)}", exc_info=True)
#         raise

# Monitoring task to check Celery status
@celery_app.task
def check_celery_status():
    logger.info("Celery health check task executed")
    return "OK"

@celery_app.task
async def periodic_sync_all_users():
    try:
        users = await UserProgress.find_all().to_list()
        
        for user in users:
            if (
                not user.last_updated or 
                datetime.utcnow() - user.last_updated > timedelta(hours=24)
            ):
                credentials = await get_user_credentials(user.user_id)
                if credentials:
                    await sync_user_leetcode_data.delay(
                        user.user_id,
                        credentials['csrf_token'],
                        credentials['cookie']
                    )
    except Exception as e:
        logger.error(f"Failed to run periodic sync: {str(e)}")
        raise

async def get_user_credentials(user_id: str):
    """
    Placeholder function - implement secure credential storage and retrieval
    """
    pass

celery_app.conf.beat_schedule = {
    'daily-user-sync': {
        'task': 'tasks.periodic_sync_all_users',
        'schedule': timedelta(hours=24),
    },
}

celery_app.conf.task_routes = {
    'tasks.sync_user_leetcode_data': {'queue': 'sync'},
    'tasks.update_user_statistics': {'queue': 'stats'},
    'tasks.periodic_sync_all_users': {'queue': 'periodic'},
}