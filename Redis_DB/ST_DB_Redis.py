# REDIS SHORT TERM DB

# BE SURE TO FIRST RUN:
    # Docker Container:
    # in cmd: docker run --name redis-stack -p 6379:6379 redis/redis-stack-server:latest

from redis.asyncio import Redis, ConnectionError
import logfire
import time
from uuid import uuid4
from typing import List
import json

# Connect to Redis:
async def redis_init() -> Redis|None:

    redis_db = Redis(host='localhost', port=6379, db=0, decode_responses=True)
    # db = 0 means default Redis logical database (database number 0).
    # decode_responses=True will return decoded string
    
    # Test Connection
    if await test_redis_conn(redis_db):
        return redis_db
    else:
        return None

async def test_redis_conn(redis_db: Redis) -> bool:
    """Function to test connection with Redis DB"""
    
    with logfire.span('redis: test connection'):
        try:
            # Test the connection with Redis DB
            response = await redis_db.ping()

            if response:
                logfire.info("Connected to Redis.")
                return True
            else:
                logfire.warn("FAILED TO CONNECT TO REDIS DB!")
                return False
            
        except ConnectionError as e:
            logfire.error(f"Redis connection error: {e}")
            return False

def make_redis_log_id() -> str:
    """ Function to generate log id in Redis DB"""

    # Microsecond timestamp
    micros_timestamp = int(time.time() * 1_000_000)

    # Short UUID suffix to guarantee uniqueness
    uuid_suffix = uuid4().hex[:6]

    return f"{micros_timestamp}:{uuid_suffix}"

async def store_log_redis(redis_db: Redis, redis_log_id: str, entry: dict) -> None:
    """Store log entry in Redis with TTL and add it to a sorted set (async)"""

    LOG_TTL = 15 * 60  # 15 minutes TTL

    with logfire.span('redis: store log'):

        # Extract time stamp from redis_log_id
        micros_timestamp = int(redis_log_id.split(":")[0])

        # Store the log entry with expiration
        await redis_db.set(redis_log_id, json.dumps(entry), ex=LOG_TTL)

        # Add to sorted set for chronological lookup
        await redis_db.zadd("temp_logs", {redis_log_id: micros_timestamp})

        logfire.info(f"{redis_log_id} added to Redis DB")

        return None

async def get_logs_before(redis_db: Redis, ref_log_id: str, num_of_logs: int = 5) -> List[dict]:

    """
    Returns up to 'num_of_logs' log entries from Redis that are strictly before the given 'ref_log_id'.

    Parameters:
        ref_log_id (str): The reference log ID in the format "timestamp:uuid".
        num_of_logs (int): Number of logs to return (default: 5).

    Returns:
        List[str]: Log entries (strings), most recent last.
    """
    
    with logfire.span('redis: get logs before'):
        try:
            ref_timestamp = int(ref_log_id.split(":")[0])
        except (IndexError, ValueError):
            raise ValueError("Invalid log ID format. Expected 'timestamp:uuid'.")

        # ascending order:
        log_ids = await redis_db.zrangebyscore(
            "temp_logs",
            min = '-inf',
            max = ref_timestamp - 1,
            start = 0,
            num = num_of_logs
        )

        # Fetch actual log values by keys
        if not log_ids:
            return []

        log_entries = await redis_db.mget(log_ids)
        
        # Return list of dicts with log_id and message, filter out missing
        recent_logs: list = [
            {"log_id": lid, "message": entry}
            for lid, entry in zip(log_ids, log_entries)
            if entry is not None
        ]
        return recent_logs

