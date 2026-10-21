"""Optional private-file coverage. Never prints or saves a vendor catalog."""

import os
from collections import Counter
from urllib.parse import quote

import httpx
import pytest

from trumpf_oseon_mcp.api.client import OseonAPIClient
from trumpf_oseon_mcp.config import Config
from trumpf_oseon_mcp.registry import OperationRegistry, METHODS


def sample(schema, registry, seen=()):
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            raise ValueError("Required recursive schema needs a supplied fixture")
        return sample(registry.resolve(schema), registry, (*seen, ref))
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type", "object")
    if kind == "object":
        return {
            name: sample(schema["properties"][name], registry, seen)
            for name in schema.get("required", [])
        }
    if kind == "array":
        return [
            sample(schema["items"], registry, seen)
            for _ in range(max(1, schema.get("minItems", 0)))
        ]
    if kind in {"integer", "number"}:
        return max(
            1, schema.get("minimum", 0) + (1 if schema.get("exclusiveMinimum") else 0)
        )
    if kind == "boolean":
        return False
    if schema.get("format") == "date-time":
        return "2026-01-01T00:00:00Z"
    if schema.get("format") == "date":
        return "2026-01-01"
    if schema.get("format") == "uuid":
        return "00000000-0000-4000-8000-000000000001"
    return "synthetic"


async def verify_document(document):
    registry = OperationRegistry(document)
    expected = {
        (m.upper(), p)
        for p, item in document["paths"].items()
        for m in item
        if m in METHODS
    }
    assert set(registry.operations) == expected
    calls = []
    config = Config(
        api_file="unused", base_url="https://synthetic.invalid", allow_writes=True
    )
    api = OseonAPIClient(
        config,
        registry,
        httpx.MockTransport(
            lambda request: calls.append(request)
            or httpx.Response(200, json={"synthetic": True})
        ),
    )
    for method, path in sorted(expected):
        operation = registry.get(method, path)
        inputs = {location: {} for location in ["path", "query", "header"]}
        body = None
        for parameter in operation.parameters:
            location = parameter["in"]
            if location == "body":
                body = sample(parameter["schema"], registry)
            elif location in inputs:
                inputs[location][parameter["name"]] = sample(parameter, registry)
        result = await api.invoke(
            method, path, inputs["path"], inputs["query"], inputs["header"], body
        )
        assert result == {"status": 200, "data": {"synthetic": True}}
        request = calls[-1]
        target = path
        for name, value in inputs["path"].items():
            target = target.replace("{" + name + "}", quote(str(value), safe=""))
        assert request.method == method
        assert request.url.path == registry.base_path + target
        assert request.url.host == "synthetic.invalid"
    assert len(calls) == len(expected)
    return Counter(method for method, _ in expected)


async def test_synthetic_all_operation_dispatch(document):
    counts = await verify_document(document)
    assert sum(counts.values()) == 12


async def test_local_api_file_coverage():
    path = os.getenv("OSEON_TEST_API_FILE")
    if not path:
        pytest.skip("Set OSEON_TEST_API_FILE for private local-file coverage")
    import json

    with open(path, encoding="utf-8-sig") as source:
        document = json.load(source)
    counts = await verify_document(document)
    expected = os.getenv("OSEON_EXPECTED_OPERATIONS")
    if expected:
        assert sum(counts.values()) == int(expected)
    print(
        "Local-file mock dispatch:",
        dict(sorted(counts.items())),
        "total:",
        sum(counts.values()),
    )
