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
    """写入一条日志到 Redis，并把它登记到时间索引里。

    存储采用"双写"结构，二者各有分工：

    1. **String 主存** —— 以 ``redis_log_id``（形如 ``微秒时间戳:6位UUID``）为 key，
       日志的 JSON 文本为 value，``ex=LOG_TTL`` 使其在 15 分钟后自动过期。
       TTL 的作用：Redis 只负责短期缓冲，长期持久化交给 PostgreSQL；
       15 分钟足够覆盖"取前 5 条上下文"的时间窗口。
       对应 Redis 命令：``SET <id> <json> EX 900``。

    2. **Sorted Set 时间索引** —— 把日志 ID 加入有序集合 ``temp_logs``，
       score 设为该日志的微秒时间戳，从而天然按时间排序。
       这样后续可以通过 ``zrangebyscore`` 按时间区间切片，取出"当前日志之前的 N 条"。
       对应 Redis 命令：``ZADD temp_logs <微秒时间戳> <id>``。
       注意：ZSET 成员本身不带 TTL，会随 key 的 String 过期而在下次查询时成为"悬空成员"
       （参见 :func:`get_logs_before` 中对 ``None`` 返回值的过滤处理）。

    id 前缀即时间戳，所以 ``int(redis_log_id.split(":")[0])`` 直接复用作 score，
    保证"插入顺序"与"时间顺序"一致。
    """
    LOG_TTL = 15 * 60  # 15 分钟

    with logfire.span('redis: store log'):
        # 从 ID 中解出微秒时间戳，作为 ZSET 的 score（按时间排序的依据）。
        micros_timestamp = int(redis_log_id.split(":")[0])

        # 写入 String 主存：key=日志ID，value=日志JSON，15 分钟后自动过期。
        await redis_db.set(redis_log_id, json.dumps(entry), ex=LOG_TTL)

        # 登记 ZSET 时间索引：成员=日志ID，score=微秒时间戳。
        await redis_db.zadd("temp_logs", {redis_log_id: micros_timestamp})

        logfire.info(f"{redis_log_id} added to Redis DB")


async def get_logs_before(
    redis_db: Redis, ref_log_id: str, num_of_logs: int = 5
) -> List[dict]:
    """取出在 ``ref_log_id`` 之前（更早）发生的最多 ``num_of_logs`` 条日志。

    用于在 LLM 分析时提供"上下文窗口"——比如 ERROR 日志触发时，
    把它前面的几条日志一起喂给智能体，帮助判断错误模式与根因。

    查询思路（基于 :func:`store_log_redis` 写入的 ZSET 索引）：

    1. 从参考 ID 解出微秒时间戳 ``ref_timestamp``。
    2. 用 ``zrangebyscore`` 在有序集合 ``temp_logs`` 中按 score（时间戳）做范围查询：
       - ``min='-inf'``：从最早一条开始；
       - ``max=ref_timestamp - 1``：严格小于当前日志（``-1`` 微秒保证不包含自身）；
       - ``start=0, num=num_of_logs``：只取前 N 条。
       对应 Redis 命令：``ZRANGEBYSCORE temp_logs -inf <ref_ts - 1> LIMIT 0 5``。
       返回的是日志 ID 列表（按时间升序）。
    3. 用 ``mget`` 一次性批量取出这些 ID 对应的 JSON 文本（一次往返，比循环 get 高效）。
       对应 Redis 命令：``MGET <id1> <id2> ...``。

    关于 ``entry is None`` 过滤：ZSET 成员不会随 String key 过期而被删除，
    因此可能出现"ID 还在索引里、但实际数据已 TTL 过期"的悬空成员，
    ``mget`` 对这种 key 返回 ``None``，这里统一过滤掉，保证返回的都是有效日志。
    """
    with logfire.span('redis: get logs before'):
        try:
            # 从 ID 还原出当前日志的微秒时间戳，作为查询上界。
            ref_timestamp = int(ref_log_id.split(":")[0])
        except (IndexError, ValueError):
            raise ValueError("Invalid log ID format. Expected 'timestamp:uuid'.")

        # 步骤一：从 ZSET 时间索引中按 score 取出最多 num_of_logs 条更早的日志 ID。
        log_ids = await redis_db.zrangebyscore(
            "temp_logs",
            min='-inf',
            max=ref_timestamp - 1,   # 严格小于当前日志（微秒级），避免取到自身。
            start=0,
            num=num_of_logs,
        )

        if not log_ids:
            return []

        # 步骤二：用 mget 一次性批量取出这些 ID 对应的 JSON 内容。
        log_entries = await redis_db.mget(log_ids)

        # 步骤三：拼接结果；过滤掉已过期（None）的悬空成员。
        return [
            {"log_id": lid, "message": entry}
            for lid, entry in zip(log_ids, log_entries)
            if entry is not None
        ]
