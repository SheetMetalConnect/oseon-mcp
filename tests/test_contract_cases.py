"""Synthetic regressions for structural cases in a supplied Swagger contract."""

import dataclasses

import httpx
import pytest

from trumpf_oseon_mcp.api.client import OseonAPIClient
from trumpf_oseon_mcp.registry import OperationRegistry


async def test_declared_not_modified_is_not_a_redirect(config, document):
    document["paths"]["/sheets"]["get"]["responses"] = {
        "304": {"description": "Cached"}
    }
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(304, headers={"location": "https://elsewhere.invalid"})

    result = await OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(respond)
    ).invoke("GET", "/sheets")
    assert result == {"status": 304, "data": None}
    assert len(calls) == 1


async def test_explicit_declared_plain_text_representation(config, document):
    operation = document["paths"]["/plain"]["post"]
    operation["consumes"] = ["application/json", "text/json", "text/plain"]

    def respond(request):
        assert request.headers["content-type"] == "text/plain"
        assert request.content == b"synthetic"
        return httpx.Response(204)

    api = OseonAPIClient(
        dataclasses.replace(config, allow_writes=True),
        OperationRegistry(document),
        httpx.MockTransport(respond),
    )
    await api.invoke("POST", "/plain", body="synthetic", content_type="text/plain")


@pytest.mark.parametrize("content_type", ["application/xml", "text/plain\r\nHost: bad"])
async def test_undeclared_body_media_rejected(config, registry, content_type):
    api = OseonAPIClient(dataclasses.replace(config, allow_writes=True), registry)
    with pytest.raises(ValueError, match="media type"):
        await api.invoke(
            "PUT",
            "/widgets/{key}",
            {"key": "x"},
            body={"quantity": 1},
            content_type=content_type,
        )


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        ({"type": "integer", "format": "int32"}, 2**31),
        ({"type": "integer", "format": "int32"}, -(2**31) - 1),
        ({"type": "integer", "format": "int64"}, 2**63),
        ({"type": "integer", "format": "int64"}, -(2**63) - 1),
        ({"type": "string", "format": "byte"}, "not base64!"),
        ({"type": "number", "format": "float"}, 1e39),
        ({"type": "number", "format": "double"}, 10**309),
    ],
)
def test_swagger_format_constraints(registry, schema, value):
    with pytest.raises(ValueError, match="schema"):
        registry.validate(value, schema)


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        ({"type": "integer", "format": "int32"}, 2**31 - 1),
        ({"type": "integer", "format": "int32"}, -(2**31)),
        ({"type": "integer", "format": "int64"}, 2**63 - 1),
        ({"type": "integer", "format": "int64"}, -(2**63)),
        ({"type": "string", "format": "byte"}, "c3ludGhldGlj"),
        ({"type": "string", "format": "byte"}, ""),
        ({"type": "number", "format": "float"}, 1.25),
        ({"type": "number", "format": "double"}, 1.25),
    ],
)
def test_valid_swagger_format_values(registry, schema, value):
    registry.validate(value, schema)


def secured_document(document):
    document["securityDefinitions"] = {"SyntheticBasic": {"type": "basic"}}
    document["security"] = [{"SyntheticBasic": []}]
    return document


@pytest.mark.parametrize("authorization", ["", "Bearer synthetic"])
async def test_required_basic_security_preflight(config, document, authorization):
    def forbidden(request):
        pytest.fail("Unsatisfied security reached HTTP")

    api = OseonAPIClient(
        dataclasses.replace(config, authorization=authorization),
        OperationRegistry(secured_document(document)),
        httpx.MockTransport(forbidden),
    )
    with pytest.raises(ValueError, match="authentication"):
        await api.invoke("GET", "/sheets")


async def test_basic_and_anonymous_security_overrides(config, document):
    secured_document(document)
    document["paths"]["/required"]["get"]["security"] = []
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(204)

    transport = httpx.MockTransport(respond)
    api = OseonAPIClient(
        dataclasses.replace(
            config, authorization="", username="synthetic", password="synthetic"
        ),
        OperationRegistry(document),
        transport,
    )
    await api.invoke("GET", "/sheets")
    assert calls[-1].headers["Authorization"].startswith("Basic ")
    anonymous = OseonAPIClient(
        dataclasses.replace(config, authorization=""),
        OperationRegistry(document),
        transport,
    )
    await anonymous.invoke("GET", "/required", query_parameters={"tenant": "synthetic"})
    assert "authorization" not in calls[-1].headers


def test_operation_description_and_response_contract(document):
    operation = document["paths"]["/sheets"]["get"]
    operation.update(
        {
            "summary": "Synthetic summary",
            "description": "Synthetic description",
            "deprecated": True,
            "responses": {
                "200": {
                    "description": "Synthetic output",
                    "schema": {"$ref": "#/definitions/Payload"},
                }
            },
        }
    )
    registry = OperationRegistry(secured_document(document))
    described = registry.describe("GET", "/sheets")
    assert described["description"] == "Synthetic description"
    assert described["summary"] == "Synthetic summary"
    assert described["deprecated"] is True
    assert described["responses"] == operation["responses"]
    assert "#/definitions/Payload" in described["schemas"]
    assert described["security"] == [{"SyntheticBasic": []}]
    assert described["security_schemes"] == {"SyntheticBasic": {"type": "basic"}}


@pytest.mark.parametrize("payload", [[], False, "synthetic", 23, 1.25, None])
async def test_json_response_root_types(config, registry, payload):
    api = OseonAPIClient(
        config,
        registry,
        httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    result = await api.invoke("GET", "/sheets")
    assert result == {"status": 200, "data": payload}


async def test_only_declared_safe_response_headers_returned(config, document):
    document["paths"]["/sheets"]["get"]["responses"] = {
        "200": {
            "description": "Synthetic response",
            "headers": {
                "ETag": {"type": "string"},
                "X-Count": {"type": "integer"},
                "Set-Cookie": {"type": "string"},
                "Authorization": {"type": "string"},
            },
        }
    }
    response = httpx.Response(
        200,
        json=False,
        headers={
            "ETag": "synthetic-tag",
            "X-Count": "3",
            "Set-Cookie": "synthetic-cookie",
            "Authorization": "synthetic-secret",
            "X-Undeclared": "synthetic",
        },
    )
    api = OseonAPIClient(
        config,
        OperationRegistry(document),
        httpx.MockTransport(lambda request: response),
    )
    result = await api.invoke("GET", "/sheets")
    assert result == {
        "status": 200,
        "data": False,
        "headers": {"ETag": "synthetic-tag", "X-Count": "3"},
    }


async def test_explicit_text_json_media(config, document):
    document["paths"]["/plain"]["post"]["consumes"] = ["application/json", "text/json"]

    def respond(request):
        assert request.headers["content-type"] == "text/json"
        assert request.content == b'"synthetic"'
        return httpx.Response(204)

    api = OseonAPIClient(
        dataclasses.replace(config, allow_writes=True),
        OperationRegistry(document),
        httpx.MockTransport(respond),
    )
    await api.invoke("POST", "/plain", body="synthetic", content_type="text/json")


async def test_undeclared_not_modified_is_an_error(config, registry):
    api = OseonAPIClient(
        config, registry, httpx.MockTransport(lambda request: httpx.Response(304))
    )
    with pytest.raises(ValueError, match="HTTP 304"):
        await api.invoke("GET", "/sheets")


async def test_default_response_can_cover_not_modified(config, document):
    document["paths"]["/sheets"]["get"]["responses"] = {
        "default": {"description": "All other response statuses"}
    }
    api = OseonAPIClient(
        config,
        OperationRegistry(document),
        httpx.MockTransport(lambda request: httpx.Response(304)),
    )
    assert await api.invoke("GET", "/sheets") == {"status": 304, "data": None}


async def test_external_bearer_satisfies_declared_oauth(config, document):
    document["securityDefinitions"] = {
        "SyntheticOAuth": {
            "type": "oauth2",
            "flow": "implicit",
            "scopes": {},
            "authorizationUrl": "https://synthetic.invalid/authorize",
        }
    }
    document["security"] = [{"SyntheticOAuth": []}]
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-secret"
        return httpx.Response(204)

    api = OseonAPIClient(
        config, OperationRegistry(document), httpx.MockTransport(respond)
    )
    await api.invoke("GET", "/sheets")
    assert len(calls) == 1


async def test_anonymous_security_alternative_needs_no_credential(config, document):
    secured_document(document)
    document["security"] = [{"SyntheticBasic": []}, {}]

    def respond(request):
        assert "Authorization" not in request.headers
        return httpx.Response(204)

    api = OseonAPIClient(
        dataclasses.replace(config, authorization=""),
        OperationRegistry(document),
        httpx.MockTransport(respond),
    )
    await api.invoke("GET", "/sheets")


@pytest.mark.parametrize(
    "authorization", ["Basic c3ludGhldGljOnN5bnRoZXRpYw==", "Bearer synthetic"]
)
async def test_basic_and_oauth_conjunction_is_not_reinterpreted_as_or(
    config, document, authorization
):
    secured_document(document)
    document["securityDefinitions"]["SyntheticOAuth"] = {
        "type": "oauth2",
        "flow": "implicit",
        "scopes": {},
        "authorizationUrl": "https://synthetic.invalid/authorize",
    }
    document["security"] = [{"SyntheticBasic": [], "SyntheticOAuth": []}]

    def forbidden(request):
        pytest.fail("Unsatisfied conjunctive security reached HTTP")

    api = OseonAPIClient(
        dataclasses.replace(config, authorization=authorization),
        OperationRegistry(document),
        httpx.MockTransport(forbidden),
    )
    with pytest.raises(ValueError, match="authentication"):
        await api.invoke("GET", "/sheets")
