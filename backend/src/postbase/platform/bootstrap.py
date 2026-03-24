from src.postbase.domain.enums import CapabilityKey
from src.postbase.platform.registry import provider_registry
from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider
from src.postbase.providers.data.postgres_native import PostgresNativeDataProvider
from src.postbase.providers.events.redis_pubsub import RedisPubSubEventsProvider
from src.postbase.providers.events.websocket_gateway import WebsocketGatewayEventsProvider
from src.postbase.providers.functions.celery_runtime import CeleryRuntimeFunctionsProvider
from src.postbase.providers.functions.inline_runtime import InlineRuntimeFunctionsProvider
from src.postbase.providers.storage.local_disk import LocalDiskStorageProvider
from src.postbase.providers.storage.s3_compatible import S3CompatibleStorageProvider


def bootstrap_postbase_runtime() -> None:
    provider_registry.register(
        CapabilityKey.AUTH,
        "local-postgres",
        lambda: LocalPostgresAuthProvider(),
    )
    provider_registry.register(
        CapabilityKey.DATA,
        "postgres-native",
        lambda: PostgresNativeDataProvider(),
    )
    provider_registry.register(
        CapabilityKey.STORAGE,
        "s3-compatible",
        lambda: S3CompatibleStorageProvider(),
    )
    provider_registry.register(
        CapabilityKey.STORAGE,
        "local-disk",
        lambda: LocalDiskStorageProvider(),
    )
    provider_registry.register(
        CapabilityKey.FUNCTIONS,
        "celery-runtime",
        lambda: CeleryRuntimeFunctionsProvider(),
    )
    provider_registry.register(
        CapabilityKey.FUNCTIONS,
        "inline-runtime",
        lambda: InlineRuntimeFunctionsProvider(),
    )
    provider_registry.register(
        CapabilityKey.EVENTS,
        "redis-pubsub",
        lambda: RedisPubSubEventsProvider(),
    )
    provider_registry.register(
        CapabilityKey.EVENTS,
        "websocket-gateway",
        lambda: WebsocketGatewayEventsProvider(),
    )
