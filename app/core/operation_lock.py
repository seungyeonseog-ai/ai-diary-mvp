"""동일 사용자의 AI 일기 동시 생성을 Redis 공유 잠금으로 막는다."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import redis.asyncio as redis

from app.config.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def diary_generation_lock(user_id: int):
    client = redis.Redis(
        host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
        socket_connect_timeout=5, socket_timeout=5,
    )
    lock = client.lock(f"diary-generation:{user_id}", timeout=120, thread_local=False)
    acquired = False
    renewal = None

    async def renew():
        while True:
            await asyncio.sleep(30)
            await lock.extend(120, replace_ttl=True)

    try:
        acquired = await lock.acquire(blocking=False)
        if not acquired:
            raise RuntimeError("Diary generation is already in progress")
        renewal = asyncio.create_task(renew())
        yield renewal
    finally:
        if renewal:
            renewal.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await renewal
        try:
            if acquired:
                try:
                    await lock.release()
                except Exception:
                    logger.warning("Diary lock release failed", exc_info=False)
        finally:
            with suppress(Exception):
                await client.aclose()
