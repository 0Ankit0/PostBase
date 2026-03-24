# Edge Cases - Security and Compliance

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Provider credential leaked in logs or traces | Account compromise | Redact secrets everywhere and use secret references rather than raw material |
| Audit trail missing for provider switchover | Compliance blind spot | Treat migration state changes as privileged immutable audit events |
| Adapter maintainer can read tenant data unintentionally | Insider-risk exposure | Separate control-plane admin privileges from tenant payload access |
| Provider lacks required compliance posture for regulated tenant | Governance failure | Model compliance attributes in provider catalog and enforce policy checks |
| Secret rotation occurs during active traffic spike | Partial outage | Support staged credential rotation and health verification before revoking prior secret |
