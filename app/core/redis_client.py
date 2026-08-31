# Plain sync Redis client for request-path counters/cooldowns. 
# Separate from Celery's own redis connection — Celery manages its connection itself (celery_app.py)
# this one is just for INCR/SETNX bookkeeping in request code.

import redis
from app.core.config import get_settings

settings = get_settings()
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)