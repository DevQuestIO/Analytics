from fastapi import FastAPI, HTTPException, Header, Query
from celery.result import AsyncResult
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
from datetime import datetime
from typing import List, Optional
from models import UserProgress, AggregatedStats
from leetcode_service import AnalyticsService
from config import init_db
from tasks import sync_user_leetcode_data, celery_app, check_celery_status
from redis_service import RedisService
from fastapi.middleware.cors import CORSMiddleware
import os
import logging

logger = logging.getLogger('devquest.api')

app = FastAPI(
    title="DevQuest Analytics Service",
    description="API for managing user progress analytics",
    version="1.0.0"
)

# Configure CORS
origins = [
    "http://localhost:3000",      # React development server
    "http://localhost:8000",      # FastAPI server
    "http://localhost:5000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5000",
    # Add your production domains here
    "https://devquest.io",
    "https://api.devquest.io",
    "https://www.devquest.io",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers,
    expose_headers=["*"]
)

@app.on_event("startup")
async def startup_event():
    await init_db()

@app.post("/api/v1/sync/{user_id}")
async def sync_user_data(
    user_id: str,
    username: str = Query(..., description="LeetCode username"),
    x_csrftoken: str = Header(..., alias="x-csrftoken"),  # Changed from csrf_token to x_csrftoken
    cookie: str = Header(..., alias="foo")
):
    logger.info(f"Received sync request for user {user_id} with username {username}")
    try:
        # Try Redis first
        redis_service = RedisService(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
        stats = await redis_service.get_aggregated_stats(user_id)
    
        if stats:
            return {
                "message": "Sync already completed",
                "stats": stats
            }
        task = sync_user_leetcode_data.delay(
            user_id=user_id,
            username=username,
            csrf_token=x_csrftoken,  # We can keep the variable name in our internal code
            cookie=cookie
        )
        logger.info(f"Successfully queued sync task {task.id} for user {user_id}")
        
        return {
            "message": "Sync initiated",
            "task_id": str(task.id)
        }
    except Exception as e:
        logger.error(f"Failed to queue sync task for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate sync"
        )

@app.get("/api/v1/sync/{user_id}/stream/{task_id}")
async def get_sync_status(user_id: str, task_id: str):
    async def event_generator():
        while True:
            # Check task status
            try:
                task = sync_user_leetcode_data.AsyncResult(task_id)
                
                if task.ready():
                    if task.successful():
                        # Fetch the final stats
                        stats = await get_stats(user_id)
                        yield {
                            "event": "complete",
                            "data": json.dumps({
                                "status": "completed",
                                "stats": stats
                            })
                        }
                        break
                    else:
                        yield {
                            "event": "error",
                            "data": json.dumps({
                                "status": "failed",
                                "error": str(task.result)
                            })
                        }
                        break
                else:
                    yield {
                        "event": "progress",
                        "data": json.dumps({
                            "status": "in_progress",
                            "timestamp": datetime.now().isoformat()
                        })
                    }
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "status": "error",
                        "error": str(e)
                    })
                }
                break

    return EventSourceResponse(event_generator())

@app.get("/api/v1/progress/{user_id}", response_model=UserProgress)
async def get_progress(user_id: str):
    user_progress = await UserProgress.find_one({"user_id": user_id})
    if not user_progress:
        raise HTTPException(status_code=404, detail="User progress not found")
    return user_progress

@app.get("/api/v1/stats/{user_id}")
async def get_stats(user_id: str):
    # Try Redis first
    redis_service = RedisService(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    stats = await redis_service.get_aggregated_stats(user_id)
    
    if stats:
        return stats

    # Fallback to MongoDB
    user_progress = await UserProgress.find_one({"user_id": user_id})
    if not user_progress:
        # call sync_user_data to fetch the data
        analytics_service = AnalyticsService()
        logger.info(f"Starting sync_user_submissions for user {user_id}")
        user_progress = await analytics_service.sync_user_submissions(
            user_id=user_id,
            csrf_token="csrf_token",
            cookie="cookie",
            username=user_id
        )
        logger.info(f"Completed sync_user_submissions for user {user_id}")
        # raise HTTPException(status_code=404, detail="User statistics not found")
    
    # Cache the stats in Redis
    await redis_service.store_aggregated_stats(user_id, user_progress.aggregated_stats.dict())
    return user_progress.aggregated_stats

@app.get("/api/v1/leaderboard", response_model=List[UserProgress])
async def get_leaderboard(limit: int = 10):
    users = await UserProgress.find_all(
        sort=[("aggregated_stats.total_solved", -1)]
    ).limit(limit).to_list()
    return users

@app.get("/api/v1/health/celery")
async def check_celery():
    """Check if Celery is working"""
    try:
        # Try to run a simple task
        result = check_celery_status.delay()
        response = result.get(timeout=5)  # Wait up to 5 seconds for result
        return {
            "status": "healthy" if response == "OK" else "unhealthy",
            "task_id": result.id,
            "result": response
        }
    except Exception as e:
        logger.error(f"Celery health check failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Celery service unhealthy: {str(e)}"
        )

@app.get("/api/v1/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get detailed task status"""
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": str(result.result) if result.ready() else None,
        "traceback": str(result.traceback) if result.failed() else None,
        "state": result.state
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)