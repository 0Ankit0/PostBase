from __future__ import annotations

DATA_CONFORMANCE_ROWS = [
    {"title": "Alpha", "category": "news", "score": 10, "note": None},
    {"title": "alpha", "category": "news", "score": 20, "note": "mixed Case"},
    {"title": "Beta", "category": "blog", "score": 30, "note": "beta note"},
    {"title": "Gamma", "category": "blog", "score": None, "note": ""},
]

DATA_CONFORMANCE_SCENARIOS = [
    {
        "name": "sort_with_null_scores",
        "filters": [],
        "sort": [{"field": "score", "direction": "asc"}, {"field": "id", "direction": "asc"}],
    },
    {
        "name": "null_note_filter",
        "filters": [{"field": "note", "op": "is_null", "value": True}],
        "sort": [{"field": "id", "direction": "asc"}],
    },
    {
        "name": "case_insensitive_contains",
        "filters": [{"field": "title", "op": "icontains", "value": "alpha"}],
        "sort": [{"field": "id", "direction": "asc"}],
    },
]
