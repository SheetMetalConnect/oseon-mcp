import dataclasses
import os
import sys

import httpx
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from trumpf_oseon_mcp.__main__ import create_server
from trumpf_oseon_mcp.api.client import OseonAPIClient


@pytest.mark.parametrize("writes", [False, True])
async def test_sdk_discovery_and_invocation(config, registry, writes):
    config = dataclasses.replace(config, allow_writes=writes)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"synthetic": True})

    api = OseonAPIClient(config, registry, httpx.MockTransport(respond))
    async with Client(create_server(config, registry, api)) as client:
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == {
            "discover_operations",
            "describe_operation",
            "invoke_operation",
            "list_work_orders",
            "list_nestings",
            "list_stock",
            "list_remainder_sheets",
        }
        invocation = next(t for t in tools if t.name == "invoke_operation")
        assert invocation.annotations.read_only_hint is not writes
        discovered = await client.call_tool(
            "discover_operations", {"query": "raw sheets"}
        )
        assert discovered.structured_content["total"] == 1
        described = await client.call_tool(
            "describe_operation", {"method": "PUT", "path": "/widgets/{key}"}
        )
        assert described.structured_content["schemas"]
        result = await client.call_tool(
            "invoke_operation", {"method": "GET", "path": "/sheets"}
        )
        assert result.structured_content == {"status": 200, "data": {"synthetic": True}}
        invalid = await client.call_tool(
            "invoke_operation", {"method": "GET", "path": "/unregistered"}
        )
        assert invalid.is_error
        blocked = await client.call_tool(
            "invoke_operation", {"method": "DELETE", "path": "/writes"}
        )
        assert blocked.is_error is not writes
        assert len(calls) == (2 if writes else 1)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_production_entrypoint_stdio(api_file, tmp_path, mode):
    env = {
        **os.environ,
        "OSEON_API_FILE": str(api_file),
        "OSEON_BASE_URL": "https://synthetic.invalid",
        "OSEON_ALLOW_WRITES": "false",
        "OSEON_AUTHORIZATION": "",
        "OSEON_USERNAME": "",
        "OSEON_PASSWORD": "",
        "OSEON_USER_HEADER": "",
        "OSEON_TERMINAL_HEADER": "",
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "trumpf_oseon_mcp"], cwd=tmp_path, env=env
    )
    async with Client(params, mode=mode, read_timeout_seconds=10) as client:
        assert len((await client.list_tools()).tools) == 7
        if mode == "auto":
            assert client.session.protocol_version == "2026-07-28"
        result = await client.call_tool("discover_operations", {"query": "jobs"})
        assert result.structured_content["total"] == 1
        invalid = await client.call_tool(
            "invoke_operation", {"method": "DELETE", "path": "/writes"}
        )
        assert invalid.is_error
        assert "OSEON_ALLOW_WRITES" in invalid.content[0].text


async def test_stdio_successful_mock_dispatch(api_file, tmp_path):
    script = """
import httpx
from trumpf_oseon_mcp.__main__ import create_server
from trumpf_oseon_mcp.config import get_config
from trumpf_oseon_mcp.registry import OperationRegistry
from trumpf_oseon_mcp.api.client import OseonAPIClient
config = get_config()
registry = OperationRegistry.load(config.api_file)
transport = httpx.MockTransport(
    lambda request: httpx.Response(200, json={"synthetic": True})
)
api = OseonAPIClient(config, registry, transport)
create_server(config, registry, api).run(transport="stdio")
"""
    env = {
        **os.environ,
        "OSEON_API_FILE": str(api_file),
        "OSEON_BASE_URL": "https://synthetic.invalid",
        "OSEON_ALLOW_WRITES": "false",
        "OSEON_AUTHORIZATION": "",
        "OSEON_USERNAME": "",
        "OSEON_PASSWORD": "",
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-c", script], env=env, cwd=tmp_path
    )
    async with Client(params, read_timeout_seconds=10) as client:
        result = await client.call_tool(
            "invoke_operation", {"method": "GET", "path": "/sheets"}
        )
        assert result.structured_content == {"status": 200, "data": {"synthetic": True}}


async def test_sdk_media_selection_and_response_metadata(config, document):
    from trumpf_oseon_mcp.registry import OperationRegistry

    operation = document["paths"]["/widgets/{key}"]["put"]
    operation["consumes"] = ["application/json", "text/json"]
    operation["responses"] = {
        "202": {
            "description": "Synthetic accepted",
            "schema": {"type": "boolean"},
            "headers": {"ETag": {"type": "string"}},
        }
    }
    registry = OperationRegistry(document)
    config = dataclasses.replace(config, allow_writes=True)

    def respond(request):
        assert request.headers["content-type"] == "text/json"
        return httpx.Response(202, json=False, headers={"ETag": "synthetic-tag"})

    api = OseonAPIClient(config, registry, httpx.MockTransport(respond))
    async with Client(create_server(config, registry, api)) as client:
        described = await client.call_tool(
            "describe_operation", {"method": "PUT", "path": "/widgets/{key}"}
        )
        assert described.structured_content["responses"] == operation["responses"]
        result = await client.call_tool(
            "invoke_operation",
            {
                "method": "PUT",
                "path": "/widgets/{key}",
                "path_parameters": {"key": "synthetic"},
                "body": {"quantity": 2},
                "content_type": "text/json",
            },
        )
        assert result.structured_content == {
            "status": 202,
            "data": False,
            "headers": {"ETag": "synthetic-tag"},
        }
