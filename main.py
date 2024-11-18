from fastapi import FastAPI, HTTPException, Header, Query
from celery.result import AsyncResult
from typing import List, Optional
from models import UserProgress, AggregatedStats
from config import init_db
from tasks import sync_user_leetcode_data, celery_app, check_celery_status
from redis_service import RedisService
import os
import logging

logger = logging.getLogger('devquest.api')

app = FastAPI(
    title="DevQuest Analytics Service",
    description="API for managing user progress analytics",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    await init_db()

@app.post("/api/v1/sync/{user_id}")
async def sync_user_data(
    user_id: str,
    username: str = Query(..., description="LeetCode username"),
    x_csrftoken: str = Header(..., alias="x-csrftoken"),  # Changed from csrf_token to x_csrftoken
    cookie: str = Header(...)
):
    logger.info(f"Received sync request for user {user_id} with username {username}")
    try:
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

@app.get("/api/v1/sync/{user_id}/status/{task_id}")
async def get_sync_status(user_id: str, task_id: str):
    try:
        task = sync_user_leetcode_data.AsyncResult(task_id)
        
        if task.ready():
            if task.successful():
                return {
                    "status": "completed",
                    "result": "Sync completed successfully"
                }
            else:
                return {
                    "status": "failed",
                    "error": str(task.result)
                }
        else:
            return {
                "status": "in_progress"
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check task status: {str(e)}"
        )

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
        raise HTTPException(status_code=404, detail="User statistics not found")
    
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