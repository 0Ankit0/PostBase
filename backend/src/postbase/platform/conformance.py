from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations

from pydantic import BaseModel, Field

from src.postbase.platform.registry import provider_registry
from src.postbase.platform.seeding import CERTIFICATION_STATES


class ProviderPairResult(BaseModel):
    capability_key: str
    provider_pair: str
    status: str
    shared_operations: list[str] = Field(default_factory=list)
    missing_operations: list[str] = Field(default_factory=list)
    badge: str


class ProviderConformanceReport(BaseModel):
    generated_at: str
    conformance_version: str
    summary: dict[str, int]
    results: list[ProviderPairResult]


class ProviderConformanceHarness:
    def run(self) -> ProviderConformanceReport:
        profiles_by_capability: dict[str, list] = {}
        for profile in provider_registry.profiles():
            profiles_by_capability.setdefault(profile.capability.value, []).append(profile)

        results: list[ProviderPairResult] = []
        summary = {"pass": 0, "fail": 0}

        for capability, profiles in profiles_by_capability.items():
            certified = [
                p
                for p in profiles
                if CERTIFICATION_STATES.get((capability, p.provider_key), None) is not None
            ]
            for left, right in combinations(sorted(certified, key=lambda p: p.provider_key), 2):
                left_ops = set(left.supported_operations)
                right_ops = set(right.supported_operations)
                shared = sorted(left_ops & right_ops)
                symmetric_gap = sorted((left_ops - right_ops) | (right_ops - left_ops))
                passed = len(symmetric_gap) == 0
                status = "pass" if passed else "fail"
                summary[status] += 1
                results.append(
                    ProviderPairResult(
                        capability_key=capability,
                        provider_pair=f"{left.provider_key}::{right.provider_key}",
                        status=status,
                        shared_operations=shared,
                        missing_operations=symmetric_gap,
                        badge="passing" if passed else "failing",
                    )
                )

        version = max((p.conformance_version for p in provider_registry.profiles()), default="unknown")
        return ProviderConformanceReport(
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            conformance_version=version,
            summary=summary,
            results=results,
        )
