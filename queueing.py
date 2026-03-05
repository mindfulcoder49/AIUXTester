import json
from typing import Optional

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from rq import Queue

from config import REDIS_URL


def get_sync_redis() -> Redis:
    # RQ stores pickled/binary payloads in Redis job hashes.
    # decode_responses must stay False or redis-py may try utf-8 decode and crash.
    return Redis.from_url(REDIS_URL, decode_responses=False)


def get_async_redis() -> AsyncRedis:
    return AsyncRedis.from_url(REDIS_URL, decode_responses=False)


def get_queue(name: str = "sessions") -> Queue:
    return Queue(name, connection=get_sync_redis(), default_timeout=7200)


def session_channel(session_id: str) -> str:
    return f"session_events:{session_id}"


def publish_event_sync(redis_conn: Redis, session_id: str, event: dict) -> None:
    redis_conn.publish(session_channel(session_id), json.dumps(event))


async def publish_event_async(redis_conn: AsyncRedis, session_id: str, event: dict) -> None:
    await redis_conn.publish(session_channel(session_id), json.dumps(event))


def redis_available() -> bool:
    try:
        conn = get_sync_redis()
        return bool(conn.ping())
    except Exception:
        return False
