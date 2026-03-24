from enum import Enum


class CapabilityKey(str, Enum):
    AUTH = "auth"
    DATA = "data"
    STORAGE = "storage"
    FUNCTIONS = "functions"
    EVENTS = "events"


class EnvironmentStage(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class BindingStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    DISABLED = "disabled"


class ProviderCertificationState(str, Enum):
    CERTIFIED = "certified"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"


class ApiKeyRole(str, Enum):
    ANON = "anon"
    SERVICE_ROLE = "service_role"


class SecretStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PolicyMode(str, Enum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    OWNER = "owner"
    SERVICE = "service"


class MigrationStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"


class SwitchoverStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
