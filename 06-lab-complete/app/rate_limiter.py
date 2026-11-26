"""Atomic 60-second sliding window, shared across workers and restarts."""
import hashlib
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_MS = 60_000
SLIDING_WINDOW = """
local clock = redis.call('TIME')
local now = clock[1] * 1000 + math.floor(clock[2] / 1000)
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
    return {0, retry}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return {1, 0}
"""


def check_rate_limit(key: str) -> None:
    # Never put the API key itself in a Redis key or log.
    identity = hashlib.sha256(key.encode("utf-8")).hexdigest()
    redis_key = f"{settings.redis_key_prefix}:rate:{identity}"
    allowed, retry_after = r.eval(
        SLIDING_WINDOW, 1, redis_key, settings.rate_limit_per_minute,
        WINDOW_MS, uuid.uuid4().hex,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
