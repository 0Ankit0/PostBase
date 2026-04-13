from __future__ import annotations

import json
from pathlib import Path
import sys


def _removed_keys(old: dict, new: dict) -> set[str]:
    return set(old.keys()) - set(new.keys())


def main() -> int:
    baseline = Path("backend/openapi/openapi-baseline.json")
    candidate = Path("backend/openapi/openapi.json")
    version_file = Path("backend/openapi/SDK_VERSION")
    migration_notice = Path("docs/system-design/implementation/release-gate-checklist.md")

    if not baseline.exists() or not candidate.exists():
        print("openapi baseline or candidate missing; skipping breaking-change gate")
        return 0

    old = json.loads(baseline.read_text(encoding="utf-8"))
    new = json.loads(candidate.read_text(encoding="utf-8"))

    removed_paths = _removed_keys(old.get("paths", {}), new.get("paths", {}))
    removed_schemas = _removed_keys(old.get("components", {}).get("schemas", {}), new.get("components", {}).get("schemas", {}))

    old_version = old.get("info", {}).get("version", "")
    new_version = new.get("info", {}).get("version", "")
    sdk_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else ""

    breaking = bool(removed_paths or removed_schemas)
    if not breaking:
        print("no schema-breaking removals detected")
        return 0

    if new_version == old_version and sdk_version == old_version and migration_notice.exists():
        print("breaking schema change detected without version bump")
        print(f"removed_paths={sorted(removed_paths)}")
        print(f"removed_schemas={sorted(removed_schemas)}")
        print("bump backend/openapi/SDK_VERSION and add migration notice updates")
        return 1

    print("breaking changes detected with version/migration signal present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
