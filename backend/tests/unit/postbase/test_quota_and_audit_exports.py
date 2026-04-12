from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from src.postbase.control_plane.service import enforce_quota_lifecycle
from src.postbase.platform.audit import build_compliance_evidence_bundle, serialize_audit_export
from src.postbase.domain.models import AuditLog


def _sample_logs() -> list[AuditLog]:
    now = datetime.now(timezone.utc)
    return [
        AuditLog(
            id=1,
            action="migration.applied",
            entity_type="schema_migration",
            entity_id="101",
            payload_json={"version": "v1"},
            created_at=now,
        ),
        AuditLog(
            id=2,
            action="secret.rotated",
            entity_type="secret",
            entity_id="77",
            payload_json={"provider": "s3-compatible"},
            created_at=now,
        ),
    ]


def test_audit_export_contains_complete_expected_fields() -> None:
    logs = _sample_logs()
    json_export = serialize_audit_export(logs, export_format="json")
    assert '"action":"migration.applied"' in json_export
    assert '"entity_type":"schema_migration"' in json_export
    assert '"payload_json":{"version":"v1"}' in json_export

    csv_export = serialize_audit_export(logs, export_format="csv")
    assert "action,entity_type,entity_id" in csv_export
    assert "migration.applied" in csv_export
    assert "secret.rotated" in csv_export


def test_compliance_bundle_includes_hash_and_signature_metadata() -> None:
    logs = _sample_logs()
    bundle = build_compliance_evidence_bundle(
        logs,
        export_format="json",
        scope="migration",
        signing_key="test-key",
    )
    assert bundle["record_count"] == 2
    assert bundle["hash_sha256"]
    assert bundle["signature_hmac_sha256"]
    assert bundle["scope"] == "migration"


@pytest.mark.parametrize(
    "usage_total,action,expected_error",
    [
        (700.0, "bindings", None),
        (1005.0, "bindings", "quota_soft_limit_controlled_degradation"),
        (1005.0, "migrations", None),
        (1300.0, "migrations", "quota_hard_limit_enforced"),
    ],
)
def test_quota_enforcement_transitions(usage_total: float, action: str, expected_error: str | None) -> None:
    if expected_error is None:
        enforce_quota_lifecycle(
            usage_total=usage_total,
            warning_threshold=750.0,
            soft_limit=1000.0,
            hard_limit=1200.0,
            action=action,
        )
        return
    with pytest.raises(HTTPException) as exc:
        enforce_quota_lifecycle(
            usage_total=usage_total,
            warning_threshold=750.0,
            soft_limit=1000.0,
            hard_limit=1200.0,
            action=action,
        )
    assert exc.value.detail["code"] == expected_error
