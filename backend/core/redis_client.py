"""Client Redis partagé (health check, et réutilisable par les features suivantes)."""

from functools import lru_cache

import redis


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    from django.conf import settings

    return redis.from_url(settings.REDIS_URL, decode_responses=True)
