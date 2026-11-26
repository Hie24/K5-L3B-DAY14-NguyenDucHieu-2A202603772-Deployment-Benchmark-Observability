"""Lazy Redis connection, bounded network waits, no in-memory fallback."""
import redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=settings.redis_connect_timeout,
    socket_timeout=settings.redis_socket_timeout,
    retry=Retry(NoBackoff(), 0),
)


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except RedisError:
        return False
