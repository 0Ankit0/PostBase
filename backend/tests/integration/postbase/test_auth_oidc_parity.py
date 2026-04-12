from src.postbase.providers.auth.local_postgres import LocalPostgresAuthProvider
from src.postbase.providers.auth.oidc_certified import OIDCStrictConfig, OIDCCertifiedAuthProvider


def test_auth_provider_local_oidc_core_parity() -> None:
    local_ops = set(LocalPostgresAuthProvider().profile().supported_operations)
    oidc_ops = set(OIDCCertifiedAuthProvider().profile().supported_operations)

    core_ops = {"login", "refresh", "me", "logout", "session_list", "session_revoke"}
    assert core_ops.issubset(local_ops)
    assert core_ops.issubset(oidc_ops)


def test_oidc_strict_config_rejects_unknown_fields() -> None:
    try:
        OIDCStrictConfig.model_validate(
            {
                "issuer_url": "https://issuer.example.com",
                "client_id": "postbase-client",
                "expected_audience": "postbase-api",
                "expected_state": "state-12345678",
                "expected_nonce": "nonce-12345678",
                "unexpected": "value",
            }
        )
    except Exception as exc:
        assert "extra" in str(exc).lower()
    else:
        raise AssertionError("OIDCStrictConfig should reject unknown fields")
