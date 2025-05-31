# REDIS impplement:

# BE SURE TO FIRST RUN:
    # Docker Container:
    # in cmd: docker run --name redis-stack -p 6379:6379 redis/redis-stack-server:latest

from redis import Redis, ConnectionError
import time
from uuid import uuid4
from typing import List

# Connect to Redis:
redis_db = Redis(host='localhost', port=6379, db=0, decode_responses=True)
# db = 0 means default Redis logical database (database number 0).
# decode_responses=True will return decoded string

# How long logs will stay in Redis db
LOG_TTL = 15 * 60  # 15 minutes TTL

def conn_to_Redis() -> bool:
    """Function to test connection with Redis DB"""
    
    try:
        # Test the connection with Redis DB
        response = redis_db.ping()
        
        if response:
            print("Connected to Redis.")
            return True
        else:
            print("FAILED TO CONNECT TO REDIS DB!")
            return False
        
    except ConnectionError as e:
        print(f"Redis connection error: {e}")
        return False

def make_red_log_id() -> tuple[int, str]:
    """ Function to generate log id in Redis DB"""

    # Microsecond timestamp
    micros_timestamp = int(time.time() * 1_000_000)

    # short UUID suffix to guarantee uniqueness
    uuid_suffix = uuid4().hex[:6]

    return micros_timestamp, uuid_suffix

def store_log_redis(entry: str) -> None:
    """Store log entry in Redis with TTL and add it to a sorted set"""

    micros_timestamp, uuid_suffix = make_red_log_id()

    redis_log_id = f"{micros_timestamp}:{uuid_suffix}"
    
    # Store the log entry with expiration
    redis_db.set(redis_log_id, entry, ex=LOG_TTL)

    # Add to sorted set for chronological lookup
    redis_db.zadd("logs:zset", {redis_log_id: micros_timestamp})

    print(f"redis_log_id :{redis_log_id}, entry: {entry}")

    return None

def get_logs_before(ref_log_id: str, count: int = 5) -> List[str]:
    """
    Returns up to `count` log entries from Redis that are strictly before the given `ref_log_id`.

    Parameters:
        ref_log_id (str): The reference log ID in the format "timestamp:uuid".
        count (int): Number of logs to return (default: 5).

    Returns:
        List[str]: Log entries (strings), most recent first.
    """
    
    try:
        ref_timestamp = int(ref_log_id.split(":")[0])
    except (IndexError, ValueError):
        raise ValueError("Invalid log ID format. Expected 'timestamp:uuid'.")

    # Get up to `count` entries with lower score than the reference
    log_ids = redis_db.zrevrangebyscore(
        "logs:zset",
        max=ref_timestamp - 1,
        min='-inf',
        start=0,
        num=count
    )

    # Fetch actual log values by keys
    if not log_ids:
        return []

    log_entries = redis_db.mget(log_ids)

    # Filter out expired (None) entries and zip with their keys
    return [
        entry for entry in log_entries
        if entry is not None
    ]

####################################################################################################################################
#TEST

logs = [
'[2025-04-25 22:35:18,082] INFO Registered signal handlers for TERM, INT, HUP (org.apache.kafka.common.utils.LoggingSignalHandler)',
'[2025-04-25 10:48:24,173] INFO [SocketServer listenerType=CONTROLLER, nodeId=1] Created data-plane acceptor and processors for endpoint : ListenerName(CONTROLLER_SSL) (kafka.network.SocketServer)',
'[2025-04-25 10:48:24,175] INFO [SharedServer id=1] Starting SharedServer (kafka.server.SharedServer)',
'[2025-04-25 10:48:24,242] INFO [LogLoader partition=__cluster_metadata-0, dir=/mnt/kafka-data/kafka-kraft-metadata] Recovering unflushed segment 124648021. 0/1 recovered for __cluster_metadata-0. (kafka.log.LogLoader)',
'[2025-04-25 10:48:24,245] INFO [LogLoader partition=__cluster_metadata-0, dir=/mnt/kafka-data/kafka-kraft-metadata] Loading producer state till offset 124648021 with message format version 2 (kafka.log.UnifiedLog$)',
'[2025-04-25 10:48:24,246] INFO [LogLoader partition=__cluster_metadata-0, dir=/mnt/kafka-data/kafka-kraft-metadata] Reloading from producer snapshot and rebuilding producer state from offset 124648021 (kafka.log.UnifiedLog$)',
'[2025-04-25 10:48:24,246] INFO Deleted producer state snapshot /mnt/kafka-data/kafka-kraft-metadata/__cluster_metadata-0/00000000000125835950.snapshot (org.apache.kafka.storage.internals.log.SnapshotFile)',
'[2025-04-25 10:48:24,255] INFO [ProducerStateManager partition=__cluster_metadata-0]Wrote producer snapshot at offset 124648021 with 0 producer ids in 6 ms. (org.apache.kafka.storage.internals.log.ProducerStateManager)'
]

for i in logs:
    store_log_redis(i)



ref_log_id = "1748687359077255:2fd979"

# Fetch logs before this log
logs = get_logs_before(ref_log_id)

for log in logs:
    print(log)



