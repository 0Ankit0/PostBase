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


class EnvironmentStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    INACTIVE = "inactive"


class ReadinessState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"
    VALIDATING = "validating"


class BindingStatus(str, Enum):
    PENDING_VALIDATION = "pending_validation"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"
    FAILED = "failed"
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
    QUEUED = "queued"
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    CANCELED = "canceled"


class SwitchoverStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CertificationTestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class CertificationApprovalState(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
