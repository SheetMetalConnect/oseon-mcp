"""Deterministic offline regression tests replacing the former live-I/O script."""

import dataclasses
import json

import httpx
import pytest

from trumpf_oseon_mcp.api.client import OseonAPIClient
from trumpf_oseon_mcp.config import Config, get_config
from trumpf_oseon_mcp.registry import OperationRegistry


def test_registry_identity_discovery_and_description(registry, api_file):
    assert len(OperationRegistry.load(api_file).operations) == 12
    assert registry.discover(query="duplicate")["total"] == 2
    assert registry.discover(query="jobs")["total"] == 1
    assert registry.discover(query="raw sheets")["total"] == 1
    page = registry.discover(limit=1)
    assert len(page["operations"]) == 1 and page["next_offset"] == 1
    assert registry.discover(offset=100)["next_offset"] is None
    description = registry.describe("put", "/widgets/{key}")
    assert description["schemas"]["#/definitions/Payload"]["required"] == ["quantity"]
    assert description["requires_write_opt_in"]


@pytest.mark.parametrize(
    "kwargs", [{"offset": -1}, {"limit": 0}, {"limit": 101}, {"method": "fake"}]
)
def test_invalid_discovery(registry, kwargs):
    with pytest.raises(ValueError):
        registry.discover(**kwargs)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "TRACE"])
async def test_write_gate_before_transport(config, registry, method):
    def forbidden(request):
        pytest.fail("Disabled mutation reached transport")

    client = OseonAPIClient(config, registry, httpx.MockTransport(forbidden))
    with pytest.raises(ValueError, match="OSEON_ALLOW_WRITES"):
        await client.invoke(method, "/writes")


async def test_request_encoding_auth_and_unmodified_json(config, registry):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.raw_path.startswith(b"/service/widgets/a%2Fb%20%3F%23%25")
        assert request.url.params.get_list("flags") == ["one", "two"]
        assert request.url.params["active"] == "false"
        assert request.url.params["limit"] == "3"
        assert request.headers["authorization"] == "Bearer synthetic-secret"
        assert request.headers["Trumpf-User"] == "synthetic-user"
        assert request.headers["Trace"] == "trace"
        return httpx.Response(
            200, json={"arbitrary": [{"label": "unmodified", "state": 123}]}
        )

    client = OseonAPIClient(config, registry, httpx.MockTransport(respond))
    result = await client.invoke(
        "get",
        "/widgets/{key}",
        {"key": "a/b ?#%"},
        {"flags": ["one", "two"], "active": False, "limit": 3},
        {"Trace": "trace"},
    )
    assert result["data"] == {"arbitrary": [{"label": "unmodified", "state": 123}]}
    assert len(calls) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "GET", "path": "/unregistered"},
        {"method": "POST", "path": "/sheets"},
        {"path_parameters": {}},
        {"path_parameters": {"key": ".."}},
        {"path_parameters": {"key": ""}},
        {"path_parameters": {"key": "x", "extra": "y"}},
        {"query_parameters": {"unknown": "x"}},
        {"query_parameters": {"limit": 6}},
        {"query_parameters": {"limit": True}},
        {"query_parameters": {"active": "true"}},
        {"query_parameters": {"flags": [4]}},
        {"header_parameters": {"Authorization": "replacement"}},
        {"header_parameters": {"Host": "evil.invalid"}},
        {"header_parameters": {"Trace": "line\r\ninjection"}},
        {"header_parameters": {"Unknown": "x"}},
        {"body": {"quantity": 1}},
    ],
)
async def test_invalid_request_never_reaches_transport(config, registry, kwargs):
    def forbidden(request):
        pytest.fail("Invalid request reached transport")

    args = {"method": "GET", "path": "/widgets/{key}", "path_parameters": {"key": "x"}}
    args.update(kwargs)
    with pytest.raises(ValueError):
        await OseonAPIClient(config, registry, httpx.MockTransport(forbidden)).invoke(
            **args
        )


async def test_required_reference(config, registry):
    with pytest.raises(ValueError, match="Missing required query"):
        await OseonAPIClient(config, registry).invoke("GET", "/required")


@pytest.mark.parametrize(
    "body", [None, {}, {"quantity": 0}, {"quantity": "1"}, {"quantity": 1, "extra": 1}]
)
async def test_body_validation(config, registry, body):
    client = OseonAPIClient(dataclasses.replace(config, allow_writes=True), registry)
    with pytest.raises(ValueError):
        await client.invoke("PUT", "/widgets/{key}", {"key": "x"}, body=body)


async def test_mutation_json_and_plain_text(config, registry):
    calls = []

    def respond(request):
        calls.append(request)
        if request.method == "PUT":
            assert json.loads(request.content) == {"quantity": 2}
            assert request.headers["content-type"] == "application/json"
        else:
            assert request.content == b"synthetic"
            assert request.headers["content-type"] == "text/plain"
        return httpx.Response(204)

    client = OseonAPIClient(
        dataclasses.replace(config, allow_writes=True),
        registry,
        httpx.MockTransport(respond),
    )
    assert await client.invoke(
        "PUT", "/widgets/{key}", {"key": "x"}, body={"quantity": 2}
    ) == {"status": 204, "data": None}
    assert await client.invoke("POST", "/plain", body="synthetic") == {
        "status": 204,
        "data": None,
    }
    assert len(calls) == 2


@pytest.mark.parametrize("status", [302, 401, 403, 404, 429, 500])
async def test_http_errors_redacted_and_no_retry(config, registry, status, caplog):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="synthetic-secret private diagnostics",
            headers={"location": "https://elsewhere.invalid"},
        )

    client = OseonAPIClient(config, registry, httpx.MockTransport(respond))
    with pytest.raises(ValueError, match=f"HTTP {status}") as error:
        await client.invoke("GET", "/sheets")
    assert "synthetic-secret" not in str(error.value) + caplog.text
    assert len(calls) == 1


async def test_timeout_redacted_no_retry(config, registry):
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic-secret")

    with pytest.raises(ValueError, match="transport failed") as error:
        await OseonAPIClient(config, registry, httpx.MockTransport(fail)).invoke(
            "GET", "/sheets"
        )
    assert "synthetic-secret" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(200, text="synthetic"), {"status": 200, "data": "synthetic"}),
        (
            httpx.Response(
                200,
                content=b"\x00\xff",
                headers={"content-type": "application/octet-stream"},
            ),
            {
                "status": 200,
                "encoding": "base64",
                "content_type": "application/octet-stream",
                "data": "AP8=",
            },
        ),
        (httpx.Response(204), {"status": 204, "data": None}),
    ],
)
async def test_response_formats(config, registry, response, expected):
    client = OseonAPIClient(
        config, registry, httpx.MockTransport(lambda request: response)
    )
    assert await client.invoke("HEAD", "/probe") == expected


async def test_invalid_json(config, registry):
    client = OseonAPIClient(
        config,
        registry,
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"private invalid",
                headers={"content-type": "application/json"},
            )
        ),
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        await client.invoke("GET", "/sheets")


async def test_basic_auth(config, registry):
    config = dataclasses.replace(
        config, authorization="", username="synthetic", password="p#!@$"
    )

    def respond(request):
        assert request.headers["authorization"] == "Basic c3ludGhldGljOnAjIUAk"
        return httpx.Response(204)

    await OseonAPIClient(config, registry, httpx.MockTransport(respond)).invoke(
        "GET", "/sheets"
    )
    assert "p#!@$" not in repr(config)


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://synthetic.invalid",
        "https://u:p@synthetic.invalid",
        "https://synthetic.invalid/path",
        "https://synthetic.invalid?q=x",
    ],
)
def test_config_origin_validation(base_url):
    with pytest.raises(ValueError):
        Config(api_file="synthetic.json", base_url=base_url)


def test_write_opt_in_exact(monkeypatch, config):
    monkeypatch.setenv("OSEON_API_FILE", config.api_file)
    monkeypatch.setenv("OSEON_BASE_URL", config.base_url)
    monkeypatch.delenv("OSEON_ALLOW_WRITES", raising=False)
    assert not get_config().allow_writes
    monkeypatch.setenv("OSEON_ALLOW_WRITES", "true")
    assert get_config().allow_writes
    monkeypatch.setenv("OSEON_ALLOW_WRITES", "yes")
    with pytest.raises(ValueError):
        get_config()


@pytest.mark.parametrize(
    "update",
    [
        {"swagger": "3.0"},
        {"definitions": {"Bad": {"$ref": "https://synthetic.invalid/schema"}}},
        {"paths": {"//evil.invalid": {"get": {}}}},
        {"paths": {"/../escape": {"get": {}}}},
    ],
)
def test_unsupported_or_unsafe_spec(document, update):
    document.update(update)
    with pytest.raises(ValueError):
        OperationRegistry(document)


def test_declared_timestamp_format(registry):
    schema = {"type": "string", "format": "date-time"}
    registry.validate("2026-01-01T00:00:00Z", schema)
    with pytest.raises(ValueError, match="declared API schema"):
        registry.validate("not-a-timestamp", schema)


@pytest.mark.parametrize(
    ("scope", "media", "expected"),
    [
        ("operation", ["application/pdf"], "application/pdf"),
        ("global", ["text/plain"], "text/plain"),
        (
            "operation",
            ["application/octet-stream", "application/json"],
            "application/octet-stream, application/json",
        ),
        ("operation", [], "*/*"),
    ],
    ids=["operation", "global", "multiple", "unspecified"],
)
async def test_accept_declared_media(config, document, scope, media, expected):
    document["produces"] = ["application/json"]
    if scope == "operation":
        document["paths"]["/sheets"]["get"]["produces"] = media
    else:
        document["produces"] = media

    def respond(request):
        assert request.headers["Accept"] == expected
        return httpx.Response(204)

    api = OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(respond)
    )
    await api.invoke("GET", "/sheets")


@pytest.mark.parametrize(
    ("fmt", "separator"),
    [(None, ","), ("csv", ","), ("pipes", "|"), ("ssv", " "), ("tsv", "\t")],
    ids=["default", "csv", "pipes", "ssv", "tsv"],
)
async def test_header_array_collection_format(config, document, fmt, separator):
    parameter = {
        "name": "Keys",
        "in": "header",
        "type": "array",
        "items": {"type": "string"},
    }
    if fmt:
        parameter["collectionFormat"] = fmt
    document["paths"]["/sheets"]["get"]["parameters"] = [parameter]

    def respond(request):
        assert request.headers["Keys"] == f"one{separator}two"
        return httpx.Response(204)

    api = OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(respond)
    )
    await api.invoke("GET", "/sheets", header_parameters={"Keys": ["one", "two"]})


@pytest.mark.parametrize(
    ("fmt", "separator"),
    [
        (None, b"%2C"),
        ("csv", b"%2C"),
        ("pipes", b"%7C"),
        ("ssv", b"%20"),
        ("tsv", b"%09"),
    ],
    ids=["default", "csv", "pipes", "ssv", "tsv"],
)
async def test_path_array_collection_format(config, document, fmt, separator):
    parameter = {
        "name": "keys",
        "in": "path",
        "required": True,
        "type": "array",
        "items": {"type": "string"},
    }
    if fmt:
        parameter["collectionFormat"] = fmt
    document["paths"]["/bundles/{keys}"] = {"get": {"parameters": [parameter]}}

    def respond(request):
        assert request.url.raw_path == b"/service/bundles/one" + separator + b"two"
        return httpx.Response(204)

    api = OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(respond)
    )
    await api.invoke("GET", "/bundles/{keys}", path_parameters={"keys": ["one", "two"]})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_nonfinite_numeric_query_never_reaches_transport(config, document, value):
    document["paths"]["/sheets"]["get"]["parameters"] = [
        {"name": "amount", "in": "query", "type": "number"}
    ]

    def forbidden(request):
        pytest.fail("Non-finite input reached transport")

    api = OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(forbidden)
    )
    with pytest.raises(ValueError, match="finite"):
        await api.invoke("GET", "/sheets", query_parameters={"amount": value})


async def test_finite_numeric_query(config, document):
    document["paths"]["/sheets"]["get"]["parameters"] = [
        {"name": "amount", "in": "query", "type": "number"}
    ]

    def respond(request):
        assert request.url.params["amount"] == "1.25"
        return httpx.Response(204)

    api = OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(respond)
    )
    await api.invoke("GET", "/sheets", query_parameters={"amount": 1.25})


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
