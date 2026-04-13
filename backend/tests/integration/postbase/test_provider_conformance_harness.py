from __future__ import annotations

from src.postbase.platform.conformance import ProviderConformanceHarness


def test_provider_conformance_harness_emits_machine_readable_results():
    report = ProviderConformanceHarness().run()
    assert "summary" in report.model_dump()
    assert report.summary["pass"] + report.summary["fail"] == len(report.results)
    assert all(result.badge in {"passing", "failing"} for result in report.results)
