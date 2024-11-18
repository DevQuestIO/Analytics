import aioredis
import json
from typing import Dict, Optional
from models import UserProgress
import logging

logger = logging.getLogger('devquest.redis')

class RedisService:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis = None

    async def get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    async def store_aggregated_stats(self, user_id: str, stats: Dict) -> None:
        try:
            redis = await self.get_redis()
            key = f"user:stats:{user_id}"
            await redis.set(key, json.dumps(stats), ex=3600)  # 1 hour expiration
            logger.info(f"Stored stats in Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to store stats in Redis: {str(e)}")
            raise

    async def get_aggregated_stats(self, user_id: str) -> Optional[Dict]:
        try:
            redis = await self.get_redis()
            key = f"user:stats:{user_id}"
            data = await redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get stats from Redis: {str(e)}")
            return None
