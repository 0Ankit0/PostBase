# Release Gate Checklist

Use this checklist before creating a release tag from a `release/*` branch.

## Required CI Gates

| Gate | Command | Required check name | Owner |
| --- | --- | --- | --- |
| Documentation validation | `make docs` | `docs` | Frontend lead |
| Deploy readiness validation | `make deploy-readiness` | `deploy-readiness` | SRE |

## Required Human Sign-Offs (pre-tag)

All sign-offs are mandatory before tagging a release.

- [ ] Backend lead sign-off (backend architecture, migrations, API compatibility)
- [ ] Frontend lead sign-off (UI/API contract compatibility, release notes accuracy)
- [ ] SRE sign-off (operational readiness, observability, rollback readiness)
- [ ] Security sign-off (vulnerability review, secrets handling, audit coverage)

## Branch Protection Requirement

`main`, `develop`, and `release/**` branch protection must require green `docs` and `deploy-readiness` checks before merge.

## Release Tagging Rule

Do not create or move a release tag until:

1. `docs` and `deploy-readiness` checks are green in CI.
2. Backend lead, frontend lead, SRE, and security sign-offs are all recorded in the release PR.
