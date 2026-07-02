"""Async Redis repository for short-term log storage (15-min TTL)."""

import json
import time
from typing import List
from uuid import uuid4

import logfire
from redis.asyncio import Redis, ConnectionError

from app import config


async def redis_init() -> Redis | None:
    """Connect to Redis, returning a client or None on failure."""
    redis_db = Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        decode_responses=True,
    )
    if await test_redis_conn(redis_db):
        return redis_db
    return None


async def test_redis_conn(redis_db: Redis) -> bool:
    with logfire.span('redis: test connection'):
        try:
            response = await redis_db.ping()
            if response:
                logfire.info("Connected to Redis.")
                return True
            logfire.warn("FAILED TO CONNECT TO REDIS DB!")
            return False
        except ConnectionError as e:
            logfire.error(f"Redis connection error: {e}")
            return False


def make_redis_log_id() -> str:
    """Generate a log ID: ``<microsecond-timestamp>:<6-hex>``."""
    micros_timestamp = int(time.time() * 1_000_000)
    uuid_suffix = uuid4().hex[:6]
    return f"{micros_timestamp}:{uuid_suffix}"


async def store_log_redis(redis_db: Redis, redis_log_id: str, entry: dict) -> None:
    """Store a log entry with TTL and index it in a sorted set by time."""
    LOG_TTL = 15 * 60  # 15 minutes

    with logfire.span('redis: store log'):
        micros_timestamp = int(redis_log_id.split(":")[0])
        await redis_db.set(redis_log_id, json.dumps(entry), ex=LOG_TTL)
        await redis_db.zadd("temp_logs", {redis_log_id: micros_timestamp})
        logfire.info(f"{redis_log_id} added to Redis DB")


async def get_logs_before(
    redis_db: Redis, ref_log_id: str, num_of_logs: int = 5
) -> List[dict]:
    """Return up to ``num_of_logs`` entries strictly before ``ref_log_id``."""
    with logfire.span('redis: get logs before'):
        try:
            ref_timestamp = int(ref_log_id.split(":")[0])
        except (IndexError, ValueError):
            raise ValueError("Invalid log ID format. Expected 'timestamp:uuid'.")

        log_ids = await redis_db.zrangebyscore(
            "temp_logs",
            min='-inf',
            max=ref_timestamp - 1,
            start=0,
            num=num_of_logs,
        )

        if not log_ids:
            return []

        log_entries = await redis_db.mget(log_ids)
        return [
            {"log_id": lid, "message": entry}
            for lid, entry in zip(log_ids, log_entries)
            if entry is not None
        ]
