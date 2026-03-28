#!/usr/bin/env python3
"""Validate minimum deploy-readiness requirements for PostBase."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _must_exist(path: Path, errors: list[str]) -> None:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        errors.append(f"Missing or empty required artifact: {path.relative_to(REPO_ROOT)}")


def main() -> int:
    errors: list[str] = []

    required_docs = [
        REPO_ROOT / "docs/system-design/implementation/implementation-playbook.md",
        REPO_ROOT / "docs/system-design/implementation/parity-implementation-checklist.md",
        REPO_ROOT / "docs/system-design/parity-matrix.md",
    ]
    for doc in required_docs:
        _must_exist(doc, errors)

    celery_app = (REPO_ROOT / "backend/src/apps/core/celery_app.py").read_text(encoding="utf-8")
    if "postbase_process_webhook_delivery_jobs_task" not in celery_app:
        errors.append("Celery beat schedule for durable webhook draining is not configured")

    tasks_py = (REPO_ROOT / "backend/src/postbase/tasks.py").read_text(encoding="utf-8")
    if "def process_webhook_delivery_jobs_task" not in tasks_py:
        errors.append("Missing PostBase webhook delivery worker task")

    api_py = (REPO_ROOT / "backend/src/postbase/control_plane/api.py").read_text(encoding="utf-8")
    if "/operations/webhooks/drain" not in api_py:
        errors.append("Missing operator drain endpoint for durable webhook queue")

    frontend_page = (
        REPO_ROOT / "frontend/src/app/(admin-dashboard)/admin/postbase/[projectId]/page.tsx"
    ).read_text(encoding="utf-8")
    if "Completion checklist" not in frontend_page or "Run now" not in frontend_page:
        errors.append("Missing admin completion checklist and run-now drain control")

    if errors:
        print("Deploy readiness validation failed:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("Deploy readiness validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
