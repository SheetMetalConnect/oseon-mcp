"""Optional private-file coverage. Never prints or saves a vendor catalog."""

import dataclasses
import json
import os
import sys
from collections import Counter
from urllib.parse import quote

from mcp import Client
from mcp.client.stdio import StdioServerParameters

import httpx
import pytest

from trumpf_oseon_mcp.api.client import OseonAPIClient
from trumpf_oseon_mcp.config import Config
from trumpf_oseon_mcp.registry import OperationRegistry, METHODS


def sample(schema, registry, seen=(), all_fields=False, writable=True):
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            raise ValueError("Required recursive schema needs a supplied fixture")
        return sample(
            registry.resolve(schema), registry, (*seen, ref), all_fields, writable
        )
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type", "object")
    if kind == "object":
        result = {}
        required = schema.get("required", [])
        for name, child in schema.get("properties", {}).items():
            if writable and child.get("readOnly"):
                continue
            if name not in required and not all_fields:
                continue
            try:
                result[name] = sample(child, registry, seen, all_fields, writable)
            except ValueError:
                if name in required:
                    raise
        extra = schema.get("additionalProperties")
        if all_fields and isinstance(extra, dict):
            result["synthetic"] = sample(extra, registry, seen, all_fields, writable)
        return result
    if kind == "array":
        return [
            sample(schema["items"], registry, seen, all_fields, writable)
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
    if schema.get("format") == "byte":
        return "c3ludGhldGlj"
    return "synthetic"


def request_inputs(operation, registry):
    inputs = {location: {} for location in ["path", "query", "header"]}
    body = None
    for parameter in operation.parameters:
        location = parameter["in"]
        if location == "body":
            body = sample(parameter["schema"], registry, all_fields=True)
        elif location in inputs:
            inputs[location][parameter["name"]] = sample(parameter, registry)
    return inputs, body


def declared_successes(operation):
    statuses = [
        int(status)
        for status in operation.definition.get("responses", {})
        if str(status).isdigit() and (200 <= int(status) < 300 or int(status) == 304)
    ]
    return statuses or [200]


def response_payload(operation, status, registry):
    if status in {204, 304} or operation.method == "HEAD":
        return None
    declaration = registry.resolve(
        operation.definition.get("responses", {}).get(str(status), {})
    )
    schema = declaration.get("schema")
    return sample(schema, registry, all_fields=True, writable=False) if schema else None


def assert_wire_request(request, operation, registry, inputs, body, content_type=None):
    target = operation.path
    for name, value in inputs["path"].items():
        target = target.replace("{" + name + "}", quote(str(value), safe=""))
    if (
        request.method != operation.method
        or request.url.path != registry.base_path + target
    ):
        raise AssertionError("Request method/path mismatch")
    if request.url.host != "synthetic.invalid":
        raise AssertionError("Request escaped the mock origin")
    requirements = operation.definition.get(
        "security", registry.document.get("security", [])
    )
    schemes = registry.document.get("securityDefinitions", {})
    if requirements and not any(not alternative for alternative in requirements):
        kinds = {
            schemes[name]["type"]
            for alternative in requirements
            for name in alternative
        }
        if kinds == {"basic"} and not request.headers.get(
            "authorization", ""
        ).startswith("Basic "):
            raise AssertionError("Declared authentication missing from request")
    for parameter in operation.parameters:
        name, location = parameter["name"], parameter["in"]
        if location not in {"query", "header"}:
            continue
        value = inputs[location][name]

        def scalar(item):
            return str(item).lower() if isinstance(item, bool) else str(item)

        if isinstance(value, list):
            values = [scalar(item) for item in value]
            if parameter.get("collectionFormat") == "multi":
                actual = request.url.params.get_list(name)
                if actual != values:
                    raise AssertionError("Repeated query serialization mismatch")
                continue
            value = {"csv": ",", "pipes": "|", "ssv": " ", "tsv": "\t"}[
                parameter.get("collectionFormat", "csv")
            ].join(values)
        else:
            value = scalar(value)
        actual = (
            request.url.params[name] if location == "query" else request.headers[name]
        )
        if actual != value:
            raise AssertionError("Parameter serialization mismatch")
    produces = operation.definition.get(
        "produces", registry.document.get("produces", [])
    )
    if request.headers["Accept"] != (", ".join(produces) if produces else "*/*"):
        raise AssertionError("Response media negotiation mismatch")
    if body is not None:
        if content_type and request.headers["content-type"] != content_type:
            raise AssertionError("Request media selection mismatch")
        if request.headers["content-type"] in {"application/json", "text/json"}:
            actual_body = json.loads(request.content)
        else:
            actual_body = request.content.decode()
        if actual_body != body:
            raise AssertionError("Request body serialization mismatch")


async def verify_document(document):
    registry = OperationRegistry(document)
    expected = {
        (m.upper(), p)
        for p, item in document["paths"].items()
        for m in item
        if m in METHODS
    }
    if set(registry.operations) != expected:
        raise AssertionError("Operation registry coverage mismatch")
    config = Config(
        api_file="unused",
        base_url="https://synthetic.invalid",
        username="synthetic",
        password="synthetic",
        allow_writes=True,
    )
    attempts = 0
    blocked = 0
    for method, path in sorted(expected):
        operation = registry.get(method, path)
        registry.describe(method, path)
        inputs, body = request_inputs(operation, registry)
        cases = [(status, None) for status in declared_successes(operation)]
        consumes = operation.definition.get("consumes", document.get("consumes", []))
        supported_media = [
            media
            for media in consumes
            if media in {"application/json", "text/json", "text/plain"}
        ]
        preferred = (
            "application/json"
            if "application/json" in supported_media
            else (supported_media[0] if supported_media else None)
        )
        if body is not None:
            cases.extend(
                (declared_successes(operation)[0], media)
                for media in supported_media
                if media != preferred
            )
        for status, media in cases:
            payload = response_payload(operation, status, registry)
            calls = []

            def respond(request):
                assert_wire_request(request, operation, registry, inputs, body, media)
                calls.append(request)
                return httpx.Response(status, json=payload)

            api = OseonAPIClient(config, registry, httpx.MockTransport(respond))
            result = await api.invoke(
                method,
                path,
                inputs["path"],
                inputs["query"],
                inputs["header"],
                body,
                content_type=media,
            )
            if result != {"status": status, "data": payload} or len(calls) != 1:
                raise AssertionError("Declared success response dispatch mismatch")
            attempts += 1
        if operation.method not in {"GET", "HEAD", "OPTIONS"}:
            calls = []
            guarded = OseonAPIClient(
                dataclasses.replace(config, allow_writes=False),
                registry,
                httpx.MockTransport(lambda request: calls.append(request)),
            )
            try:
                await guarded.invoke(
                    method,
                    path,
                    inputs["path"],
                    inputs["query"],
                    inputs["header"],
                    body,
                )
            except ValueError as error:
                if "OSEON_ALLOW_WRITES" not in str(error):
                    raise AssertionError(
                        "Mutation failed outside the write gate"
                    ) from None
                blocked += 1
            else:
                raise AssertionError("Default write gate did not reject a mutation")
            if calls:
                raise AssertionError("Default write gate reached HTTP")
    return Counter(method for method, _ in expected), attempts, blocked


async def verify_stdio(path):
    registry = OperationRegistry.load(path)
    script = """
import os
import logging
import httpx
from trumpf_oseon_mcp.__main__ import create_server
from trumpf_oseon_mcp.config import Config
from trumpf_oseon_mcp.registry import OperationRegistry
from trumpf_oseon_mcp.api.client import OseonAPIClient
from tests.test_local_api import request_inputs, declared_successes
from tests.test_local_api import response_payload, assert_wire_request
config = Config(api_file=os.environ['OSEON_TEST_API_FILE'],
                base_url='https://synthetic.invalid', username='synthetic',
                password='synthetic', allow_writes=True)
registry = OperationRegistry.load(config.api_file)
operations = iter(sorted(registry.operations))
def respond(request):
    operation = registry.get(*next(operations))
    inputs, body = request_inputs(operation, registry)
    assert_wire_request(request, operation, registry, inputs, body)
    status = declared_successes(operation)[0]
    return httpx.Response(status, json=response_payload(operation, status, registry))
api = OseonAPIClient(config, registry, httpx.MockTransport(respond))
server = create_server(config, registry, api)
for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
    logging.getLogger(name).setLevel(logging.WARNING)
server.run(transport='stdio')
"""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", script],
        env={**os.environ, "OSEON_TEST_API_FILE": str(path)},
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    async with Client(params, read_timeout_seconds=30) as client:
        tools = (await client.list_tools()).tools
        if {tool.name for tool in tools} != {
            "discover_operations",
            "describe_operation",
            "invoke_operation",
        }:
            raise AssertionError("Unexpected MCP tool surface")
        discovered = set()
        offset = 0
        while True:
            result = await client.call_tool(
                "discover_operations", {"offset": offset, "limit": 100}
            )
            data = result.structured_content
            discovered.update(
                (item["method"], item["path"]) for item in data["operations"]
            )
            offset = data["next_offset"]
            if offset is None:
                break
        if discovered != set(registry.operations):
            raise AssertionError("Stdio discovery coverage mismatch")
        for method, path_template in sorted(registry.operations):
            operation = registry.get(method, path_template)
            described = await client.call_tool(
                "describe_operation", {"method": method, "path": path_template}
            )
            if described.is_error or described.structured_content["responses"] != (
                operation.definition.get("responses", {})
            ):
                raise AssertionError("Stdio description contract mismatch")
            inputs, body = request_inputs(operation, registry)
            result = await client.call_tool(
                "invoke_operation",
                {
                    "method": method,
                    "path": path_template,
                    "path_parameters": inputs["path"],
                    "query_parameters": inputs["query"],
                    "header_parameters": inputs["header"],
                    "body": body,
                },
            )
            status = declared_successes(operation)[0]
            expected = {
                "status": status,
                "data": response_payload(operation, status, registry),
            }
            if result.is_error or result.structured_content != expected:
                raise AssertionError("Stdio invocation contract mismatch")
    return len(discovered)


async def test_synthetic_all_operation_dispatch(document):
    counts, attempts, blocked = await verify_document(document)
    assert sum(counts.values()) == 12 and attempts == 12 and blocked == 7


async def test_local_api_file_coverage():
    path = os.getenv("OSEON_TEST_API_FILE")
    if not path:
        pytest.skip("Set OSEON_TEST_API_FILE for private local-file coverage")
    import json

    with open(path, encoding="utf-8-sig") as source:
        document = json.load(source)
    try:
        counts, attempts, blocked = await verify_document(document)
    except Exception as error:
        pytest.fail(
            f"Private contract dispatch failed: {type(error).__name__}", pytrace=False
        )
    expected = os.getenv("OSEON_EXPECTED_OPERATIONS")
    if expected:
        assert sum(counts.values()) == int(expected)
    print(
        "Local-file mock dispatch:",
        dict(sorted(counts.items())),
        "total:",
        sum(counts.values()),
        "supported media/status cases:",
        attempts,
        "default blocked mutations:",
        blocked,
    )


async def test_synthetic_stdio_contract_dispatch(api_file, capfd):
    assert await verify_stdio(api_file) == 12
    output = capfd.readouterr()
    assert output.out == "" and output.err == ""


async def test_local_api_stdio_contract_dispatch(capfd):
    path = os.getenv("OSEON_TEST_API_FILE")
    if not path:
        pytest.skip("Set OSEON_TEST_API_FILE for private stdio coverage")
    try:
        count = await verify_stdio(path)
    except Exception as error:
        pytest.fail(
            f"Private stdio dispatch failed: {type(error).__name__}", pytrace=False
        )
    expected = os.getenv("OSEON_EXPECTED_OPERATIONS")
    if expected:
        assert count == int(expected)
    print("Local-file actual stdio discovery/description/invocation:", count)
