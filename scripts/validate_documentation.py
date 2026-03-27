#!/usr/bin/env python3
"""Validate PostBase documentation completeness and minimum quality."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
SYSTEM_DESIGN_ROOT = DOCS_ROOT / "system-design"

REQUIRED_ROOT_DOCS = [
    DOCS_ROOT / "README.md",
    SYSTEM_DESIGN_ROOT / "README.md",
    SYSTEM_DESIGN_ROOT / "parity-matrix.md",
]

REQUIRED_SYSTEM_DESIGN_FILES = {
    "requirements": ["requirements-document.md", "user-stories.md"],
    "analysis": [
        "use-case-diagram.md",
        "use-case-descriptions.md",
        "system-context-diagram.md",
        "activity-diagram.md",
        "bpmn-swimlane-diagram.md",
        "data-dictionary.md",
        "business-rules.md",
        "event-catalog.md",
    ],
    "high-level-design": [
        "system-sequence-diagram.md",
        "domain-model.md",
        "data-flow-diagram.md",
        "architecture-diagram.md",
        "c4-context-container.md",
    ],
    "detailed-design": [
        "class-diagram.md",
        "sequence-diagram.md",
        "state-machine-diagram.md",
        "erd-database-schema.md",
        "component-diagram.md",
        "api-design.md",
        "c4-component.md",
    ],
    "infrastructure": [
        "deployment-diagram.md",
        "network-infrastructure.md",
        "cloud-architecture.md",
    ],
    "edge-cases": [
        "README.md",
        "provider-selection-and-provisioning.md",
        "auth-and-tenancy.md",
        "data-api-and-schema.md",
        "storage-and-file-providers.md",
        "functions-and-jobs.md",
        "realtime-and-messaging.md",
        "api-and-sdk.md",
        "security-and-compliance.md",
        "operations.md",
    ],
    "implementation": [
        "code-guidelines.md",
        "c4-code-diagram.md",
        "implementation-playbook.md",
    ],
}

REQUIRED_HEADINGS = {
    "docs/README.md": ["Documentation Map", "Validation", "Status Legend"],
    "docs/system-design/README.md": [
        "Documentation Structure",
        "Key Features",
        "Getting Started",
        "Documentation Status",
    ],
    "docs/system-design/parity-matrix.md": [
        "Status",
        "Capability and Workflow Parity",
        "Advertised API Shape Parity",
    ],
}

PARITY_ALLOWED = {"implemented", "partial", "planned"}


def is_empty(path: Path) -> bool:
    return not path.exists() or not path.read_text(encoding="utf-8").strip()


def validate_mermaid(path: Path, errors: list[str]) -> None:
    if "```mermaid" not in path.read_text(encoding="utf-8"):
        errors.append(f"Diagram file missing Mermaid content: {path.relative_to(REPO_ROOT)}")


def validate_required_headings(path: Path, headings: list[str], errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for heading in headings:
        if f"## {heading}" not in text:
            errors.append(f"{path.relative_to(REPO_ROOT)} missing heading: {heading}")


def validate_parity_markers(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    statuses = {match.group(1) for match in re.finditer(r"\|\s*(implemented|partial|planned)\s*\|", text)}
    missing = PARITY_ALLOWED - statuses
    if missing:
        errors.append(
            f"{path.relative_to(REPO_ROOT)} missing parity status marker(s): {', '.join(sorted(missing))}"
        )


def main() -> int:
    errors: list[str] = []

    for path in REQUIRED_ROOT_DOCS:
        if is_empty(path):
            errors.append(f"Missing or empty required doc: {path.relative_to(REPO_ROOT)}")

    for relative_path, headings in REQUIRED_HEADINGS.items():
        path = REPO_ROOT / relative_path
        if not path.exists():
            errors.append(f"Missing file required for heading validation: {relative_path}")
            continue
        validate_required_headings(path, headings, errors)

    for directory, filenames in REQUIRED_SYSTEM_DESIGN_FILES.items():
        dir_path = SYSTEM_DESIGN_ROOT / directory
        if not dir_path.exists():
            errors.append(f"Missing directory: {dir_path.relative_to(REPO_ROOT)}")
            continue

        for filename in filenames:
            path = dir_path / filename
            if is_empty(path):
                errors.append(f"Missing or empty file: {path.relative_to(REPO_ROOT)}")
                continue
            if "diagram" in filename or filename.startswith("c4-"):
                validate_mermaid(path, errors)

    parity_path = SYSTEM_DESIGN_ROOT / "parity-matrix.md"
    if parity_path.exists():
        validate_parity_markers(parity_path, errors)

    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Documentation validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
