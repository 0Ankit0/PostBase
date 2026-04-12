"""Auth provider adapters."""

from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider
from src.postbase.providers.auth.oidc_certified import OIDCCertifiedAuthProvider

__all__ = ["LocalPostgresAuthProvider", "OIDCCertifiedAuthProvider"]
