class PostBaseError(Exception):
    """Base exception for PostBase-specific failures."""


class ProviderResolutionError(PostBaseError):
    """Raised when a capability provider cannot be resolved."""


class AccessDeniedError(PostBaseError):
    """Raised when a caller cannot access a resource."""


class InvalidConfigurationError(PostBaseError):
    """Raised when metadata/configuration is invalid."""
