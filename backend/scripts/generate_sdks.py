from __future__ import annotations

import json
from pathlib import Path


HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _iter_operations(spec: dict) -> list[tuple[str, str, str]]:
    operations: list[tuple[str, str, str]] = []
    for path, path_item in spec.get("paths", {}).items():
        for method in HTTP_METHODS:
            op = path_item.get(method)
            if not op:
                continue
            op_id = op.get("operationId") or f"{method}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"
            operations.append((op_id, method.upper(), path))
    return sorted(operations, key=lambda item: item[0])


def _generate_typescript(spec: dict, output_path: Path) -> None:
    operations = _iter_operations(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "/* Auto-generated from backend/openapi/openapi.json. */",
        "export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';",
        "",
        "export interface RequestOptions {",
        "  query?: Record<string, string | number | boolean | null | undefined>;",
        "  body?: unknown;",
        "  headers?: Record<string, string>;",
        "}",
        "",
        "export interface Transport {",
        "  request<T = unknown>(method: HttpMethod, path: string, options?: RequestOptions): Promise<T>;",
        "}",
        "",
        "export class PostBaseSdkClient {",
        "  constructor(private readonly transport: Transport) {}",
        "",
    ]
    for op_id, method, path in operations:
        lines.extend(
            [
                f"  {op_id}(options: RequestOptions = {{}}): Promise<unknown> {{",
                f"    return this.transport.request('{method}', '{path}', options);",
                "  }",
                "",
            ]
        )
    lines.append("}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _generate_python(spec: dict, output_path: Path) -> None:
    operations = _iter_operations(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '"""Auto-generated from backend/openapi/openapi.json."""',
        "",
        "from __future__ import annotations",
        "",
        "from collections.abc import Mapping",
        "from typing import Any",
        "",
        "import httpx",
        "",
        "",
        "class PostBaseSdkClient:",
        "    def __init__(self, base_url: str, *, headers: Mapping[str, str] | None = None) -> None:",
        "        self._client = httpx.AsyncClient(base_url=base_url, headers=dict(headers or {}))",
        "",
        "    async def close(self) -> None:",
        "        await self._client.aclose()",
        "",
    ]
    for op_id, method, path in operations:
        lines.extend(
            [
                f"    async def {op_id}(self, *, params: Mapping[str, Any] | None = None, body: Any = None) -> Any:",
                f"        response = await self._client.request('{method}', '{path}', params=params, json=body)",
                "        response.raise_for_status()",
                "        if not response.content:",
                "            return None",
                "        return response.json()",
                "",
            ]
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate(spec_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    _generate_typescript(spec, Path("sdk/typescript/src/client.ts"))
    _generate_python(spec, Path("sdk/python/postbase_sdk/client.py"))


if __name__ == "__main__":
    generate(Path("backend/openapi/openapi.json"))
    print("generated sdk/typescript/src/client.ts")
    print("generated sdk/python/postbase_sdk/client.py")
