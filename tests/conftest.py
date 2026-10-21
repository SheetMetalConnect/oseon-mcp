import json
import logging
import socket

import pytest

from trumpf_oseon_mcp.config import Config
from trumpf_oseon_mcp.registry import OperationRegistry


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Offline tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture
def document():
    return {
        "swagger": "2.0",
        "basePath": "/service",
        "definitions": {
            "Payload": {
                "type": "object",
                "required": ["quantity"],
                "properties": {"quantity": {"type": "integer", "minimum": 1}},
                "additionalProperties": False,
            }
        },
        "parameters": {
            "Tenant": {
                "name": "tenant",
                "in": "query",
                "type": "string",
                "required": True,
            }
        },
        "paths": {
            "/widgets/{key}": {
                "parameters": [
                    {"name": "key", "in": "path", "required": True, "type": "string"},
                    {"name": "limit", "in": "query", "type": "integer", "maximum": 50},
                ],
                "get": {
                    "operationId": "duplicate",
                    "tags": ["Synthetic jobs"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                        },
                        {
                            "name": "flags",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {"name": "active", "in": "query", "type": "boolean"},
                        {"name": "Trumpf-User", "in": "header", "type": "string"},
                        {"name": "Trace", "in": "header", "type": "string"},
                    ],
                },
                "put": {
                    "operationId": "update",
                    "consumes": ["application/json"],
                    "parameters": [
                        {
                            "name": "payload",
                            "in": "body",
                            "required": True,
                            "schema": {"$ref": "#/definitions/Payload"},
                        }
                    ],
                },
            },
            "/sheets": {
                "get": {
                    "operationId": "duplicate",
                    "tags": ["Synthetic raw sheets"],
                    "parameters": [],
                }
            },
            "/required": {"get": {"parameters": [{"$ref": "#/parameters/Tenant"}]}},
            "/plain": {
                "post": {
                    "consumes": ["text/plain"],
                    "parameters": [
                        {
                            "name": "payload",
                            "in": "body",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                }
            },
            "/writes": {
                m: {"parameters": []}
                for m in ["post", "put", "patch", "delete", "trace"]
            },
            "/probe": {m: {"parameters": []} for m in ["head", "options"]},
        },
    }


@pytest.fixture
def registry(document):
    return OperationRegistry(document)


@pytest.fixture
def config():
    return Config(
        api_file="unused.json",
        base_url="https://synthetic.invalid",
        authorization="Bearer synthetic-secret",
        user_header="synthetic-user",
    )


@pytest.fixture
def api_file(document, tmp_path):
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(document))
    return path


@pytest.fixture(autouse=True)
def quiet_http_logs(monkeypatch):
    for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.WARNING)
