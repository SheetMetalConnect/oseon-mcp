import dataclasses
import socket

import httpx
import pytest

from trumpf_oseon_mcp.config import Config
from trumpf_oseon_mcp.api.client import OseonAPIClient
from trumpf_oseon_mcp.registry import OperationRegistry


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"swagger": "2.0"},
        {"swagger": "2.0", "paths": []},
        {"swagger": "2.0", "paths": {"/synthetic": None}},
        {"swagger": "2.0", "paths": {"/synthetic": {"get": None}}},
    ],
)
def test_malformed_document_structure_is_rejected(document):
    with pytest.raises(ValueError):
        OperationRegistry(document)


@pytest.mark.parametrize(
    "definitions",
    [
        {},
        {"Broken": {"$ref": "#/definitions/Broken"}},
        {
            "Broken": {"$ref": "#/definitions/Other"},
            "Other": {"$ref": "#/definitions/Broken"},
        },
        {"Broken": {"allOf": [{"$ref": "#/definitions/Broken"}]}},
    ],
    ids=["missing", "direct-cycle", "indirect-cycle", "composition-cycle"],
)
async def test_bad_local_schema_references_are_sanitized_before_io(
    config, document, monkeypatch, definitions
):
    network_attempts = []
    transport_calls = []

    def forbidden_network(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError("Schema validation attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    document["definitions"] = definitions
    document["paths"]["/widgets/{key}"]["put"]["parameters"][0]["schema"] = {
        "$ref": "#/definitions/Broken"
    }
    with pytest.raises(ValueError) as error:
        registry = OperationRegistry(document)
        api = OseonAPIClient(
            dataclasses.replace(config, allow_writes=True),
            registry,
            httpx.MockTransport(lambda request: transport_calls.append(request)),
        )
        await api.invoke("PUT", "/widgets/{key}", {"key": "synthetic"}, body={})
    assert "Broken" not in str(error.value)
    assert network_attempts == transport_calls == []


@pytest.mark.parametrize("ref", ["#/definitions/Missing", "https://synthetic.invalid"])
def test_standalone_schema_references_are_local_and_resolvable(registry, ref):
    with pytest.raises(ValueError) as error:
        registry.validate({}, {"$ref": ref})
    assert ref not in str(error.value)


def test_finite_recursive_schema_still_validates(document):
    document["definitions"]["Node"] = {
        "type": "object",
        "properties": {"child": {"$ref": "#/definitions/Node"}},
        "additionalProperties": False,
    }
    registry = OperationRegistry(document)
    registry.validate({"child": {"child": {}}}, {"$ref": "#/definitions/Node"})


@pytest.mark.parametrize(
    "origin",
    [
        "https://synthetic.invalid:bad",
        "https://synthetic.invalid:99999",
        "https://synthetic.invalid?",
        "https://synthetic.invalid#",
        "https://synthetic.invalid\n",
        "https://[synthetic.invalid",
        "https://synthetic.invalid\\path",
    ],
)
def test_malformed_origins_do_not_expose_values(origin):
    with pytest.raises(ValueError) as error:
        Config(api_file="synthetic.json", base_url=origin)
    assert "synthetic.invalid" not in str(error.value)


@pytest.mark.parametrize("payload", [b"NaN", b"Infinity", b"-Infinity", b"1e999"])
async def test_nonfinite_response_json_is_sanitized(config, registry, payload):
    api = OseonAPIClient(
        config,
        registry,
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=payload, headers={"content-type": "application/json"}
            )
        ),
    )
    with pytest.raises(ValueError, match="invalid JSON") as error:
        await api.invoke("GET", "/sheets")
    assert payload.decode() not in str(error.value)


@pytest.mark.parametrize("override", [False, True])
async def test_booking_headers_match_declared_names_case_insensitively(
    config, document, override
):
    document["paths"]["/sheets"]["get"]["parameters"] = [
        {"name": "trumpf-user", "in": "header", "type": "string", "required": True},
        {
            "name": "TRUMPF-TERMINAL",
            "in": "header",
            "type": "string",
            "required": True,
        },
    ]

    def respond(request):
        assert request.headers["trumpf-user"] == (
            "synthetic-override" if override else "synthetic-user"
        )
        assert request.headers["trumpf-terminal"] == "synthetic-terminal"
        return httpx.Response(204)

    api = OseonAPIClient(
        dataclasses.replace(config, terminal_header="synthetic-terminal"),
        OperationRegistry(document),
        httpx.MockTransport(respond),
    )
    await api.invoke(
        "GET",
        "/sheets",
        header_parameters={"TRUMPF-USER": "synthetic-override"} if override else {},
    )


def test_operation_header_overrides_inherited_header_case_insensitively(document):
    document["paths"]["/sheets"]["parameters"] = [
        {"name": "Trace", "in": "header", "type": "string", "required": True}
    ]
    document["paths"]["/sheets"]["get"]["parameters"] = [
        {"name": "trace", "in": "header", "type": "string", "required": False}
    ]
    operation = OperationRegistry(document).get("GET", "/sheets")
    assert operation.parameters == (
        {"name": "trace", "in": "header", "type": "string", "required": False},
    )


async def test_duplicate_header_spellings_rejected_before_transport(config, registry):
    with pytest.raises(ValueError, match="Duplicate HTTP header"):
        await OseonAPIClient(config, registry).invoke(
            "GET",
            "/widgets/{key}",
            {"key": "synthetic"},
            header_parameters={"Trace": "one", "trace": "two"},
        )


async def test_declared_header_token_characters(config, document):
    document["paths"]["/sheets"]["get"]["parameters"] = [
        {"name": "X_Correlation", "in": "header", "type": "string"}
    ]

    def respond(request):
        assert request.headers["X_Correlation"] == "synthetic"
        return httpx.Response(204)

    await OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(respond)
    ).invoke("GET", "/sheets", header_parameters={"x_correlation": "synthetic"})


@pytest.mark.parametrize("name", ["api-version", "API-Version"])
@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("version", ["synthetic-v1", "synthetic-v2", ""])
async def test_configured_api_version_follows_declared_schema(
    config, document, name, required, version
):
    document["paths"]["/sheets"]["get"]["parameters"] = [
        {
            "name": name,
            "in": "header",
            "type": "string",
            "enum": ["synthetic-v1"],
            "required": required,
        }
    ]
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers.get_list("api-version") == ["synthetic-v1"]
        return httpx.Response(204)

    api = OseonAPIClient(
        dataclasses.replace(config, api_version=version),
        OperationRegistry(document),
        httpx.MockTransport(respond),
    )
    if version == "synthetic-v1":
        assert await api.invoke("GET", "/sheets") == {"status": 204, "data": None}
        assert len(calls) == 1
    else:
        with pytest.raises(ValueError, match="declared API schema"):
            await api.invoke("GET", "/sheets")
        assert calls == []


@pytest.mark.parametrize("name", ["api-version", "API-Version"])
async def test_declared_api_version_still_cannot_be_overridden(config, document, name):
    document["paths"]["/sheets"]["get"]["parameters"] = [
        {"name": "api-version", "in": "header", "type": "string", "required": True}
    ]

    def forbidden(request):
        pytest.fail("Protected API version override reached HTTP")

    api = OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(forbidden)
    )
    with pytest.raises(ValueError, match="cannot be supplied by tools"):
        await api.invoke("GET", "/sheets", header_parameters={name: "replacement"})
