from __future__ import annotations

import json
from pathlib import Path

from src.postbase.platform.conformance import ProviderConformanceHarness


if __name__ == "__main__":
    harness = ProviderConformanceHarness()
    result = harness.run()
    output = Path("backend/artifacts/provider-conformance.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {output}")
