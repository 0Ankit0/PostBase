from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, TypeVar

from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, TimeoutError as RedisTimeoutError

from src.apps.observability.service import record_cache_metric
from src.apps.core.config import settings

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class CacheOperationResult:
    success: bool
    error_type: str | None = None
    attempts: int = 1


class RedisCache:
    """Redis cache client for production environment"""

    _pool: Optional[ConnectionPool] = None
    _client: Optional[Redis] = None
    _max_attempts: int = 3
    _retry_delay_seconds: float = 0.05
    
    @classmethod
    async def get_client(cls) -> Optional[Redis]:
        """Get Redis client instance, only in production"""
        if settings.DEBUG:
            return None
        assert settings.REDIS_URL, "REDIS_URL must be set in production"

        if cls._client is None:
            cls._pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
            )
            cls._client = Redis(connection_pool=cls._pool)

        return cls._client

    @staticmethod
    def _namespace_from_key(key: str) -> str:
        if not key:
            return "unknown"
        return key.split(":", 1)[0]

    @classmethod
    async def _with_retry(
        cls,
        *,
        operation: str,
        key: str,
        runner: Callable[[], Awaitable[T]],
    ) -> tuple[T | None, CacheOperationResult]:
        namespace = cls._namespace_from_key(key)
        attempts = 0
        while attempts < cls._max_attempts:
            attempts += 1
            try:
                value = await runner()
                record_cache_metric(
                    operation=operation,
                    outcome="success",
                    namespace=namespace,
                    attempts=attempts,
                )
                return value, CacheOperationResult(success=True, attempts=attempts)
            except (RedisTimeoutError, RedisConnectionError) as exc:
                if attempts >= cls._max_attempts:
                    log.warning(
                        "Redis cache %s failed after retries for key namespace=%s",
                        operation,
                        namespace,
                        exc_info=exc,
                    )
                    record_cache_metric(
                        operation=operation,
                        outcome="timeout" if isinstance(exc, RedisTimeoutError) else "failure",
                        namespace=namespace,
                        error_type=type(exc).__name__,
                        attempts=attempts,
                    )
                    return None, CacheOperationResult(
                        success=False,
                        error_type=type(exc).__name__,
                        attempts=attempts,
                    )
                await asyncio.sleep(cls._retry_delay_seconds * attempts)
            except RedisError as exc:
                log.warning(
                    "Redis cache %s failed for key namespace=%s",
                    operation,
                    namespace,
                    exc_info=exc,
                )
                record_cache_metric(
                    operation=operation,
                    outcome="failure",
                    namespace=namespace,
                    error_type=type(exc).__name__,
                    attempts=attempts,
                )
                return None, CacheOperationResult(
                    success=False,
                    error_type=type(exc).__name__,
                    attempts=attempts,
                )
        return None, CacheOperationResult(success=False, error_type="RetryExhausted", attempts=attempts)
    
    @classmethod
    async def close(cls):
        """Close Redis connection"""
        if cls._client:
            await cls._client.close()
            cls._client = None
        if cls._pool:
            await cls._pool.disconnect()
            cls._pool = None
    
    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        """Get value from cache"""
        client = await cls.get_client()
        if not client:
            return None

        try:
            value, result = await cls._with_retry(
                operation="get",
                key=key,
                runner=lambda: client.get(key),
            )
            if not result.success or not value:
                return None
            return json.loads(value)
        except json.JSONDecodeError as exc:
            namespace = cls._namespace_from_key(key)
            log.warning(
                "Redis cache get returned invalid JSON for key namespace=%s",
                namespace,
                exc_info=exc,
            )
            record_cache_metric(
                operation="get",
                outcome="failure",
                namespace=namespace,
                error_type=type(exc).__name__,
                attempts=1,
            )
        except TypeError as exc:
            namespace = cls._namespace_from_key(key)
            log.warning(
                "Redis cache get received unsupported payload for key namespace=%s",
                namespace,
                exc_info=exc,
            )
            record_cache_metric(
                operation="get",
                outcome="failure",
                namespace=namespace,
                error_type=type(exc).__name__,
                attempts=1,
            )
        return None

    @classmethod
    async def set(cls, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache with TTL (default 1 hour)"""
        client = await cls.get_client()
        if not client:
            return False

        namespace = cls._namespace_from_key(key)
        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError) as exc:
            log.warning(
                "Redis cache set serialization failed for key namespace=%s",
                namespace,
                exc_info=exc,
            )
            record_cache_metric(
                operation="set",
                outcome="failure",
                namespace=namespace,
                error_type=type(exc).__name__,
                attempts=1,
            )
            return False

        _, result = await cls._with_retry(
            operation="set",
            key=key,
            runner=lambda: client.setex(key, ttl, serialized),
        )
        return result.success

    @classmethod
    async def delete(cls, key: str) -> bool:
        """Delete value from cache"""
        client = await cls.get_client()
        if not client:
            return False

        _, result = await cls._with_retry(
            operation="delete",
            key=key,
            runner=lambda: client.delete(key),
        )
        return result.success

    @classmethod
    async def exists(cls, key: str) -> bool:
        """Check if key exists in cache"""
        client = await cls.get_client()
        if not client:
            return False

        value, result = await cls._with_retry(
            operation="exists",
            key=key,
            runner=lambda: client.exists(key),
        )
        return bool(value) if result.success else False

    @classmethod
    async def clear_pattern(cls, pattern: str) -> int:
        """Clear all keys matching pattern"""
        client = await cls.get_client()
        if not client:
            return 0

        async def _runner() -> int:
            keys = []
            async for matched_key in client.scan_iter(match=pattern):
                keys.append(matched_key)
            if keys:
                return await client.delete(*keys)
            return 0

        value, result = await cls._with_retry(
            operation="clear_pattern",
            key=pattern,
            runner=_runner,
        )
        return int(value or 0) if result.success else 0
