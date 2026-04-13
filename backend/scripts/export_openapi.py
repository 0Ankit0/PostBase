from __future__ import annotations

import json
from pathlib import Path


def export_openapi(output_path: Path) -> None:
    from src.main import app

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = app.openapi()
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    target = Path("backend/openapi/openapi.json")
    export_openapi(target)
    print(f"exported OpenAPI schema -> {target}")
