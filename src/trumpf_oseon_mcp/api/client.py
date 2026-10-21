"""Validated registry dispatch with one HTTP attempt and sanitized failures."""

import base64
from typing import Any
from urllib.parse import quote

import httpx

from ..config import Config
from ..registry import OperationRegistry, READ_METHODS


class OseonAPIClient:
    def __init__(
        self,
        config: Config,
        registry: OperationRegistry,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config
        self.registry = registry
        self.transport = transport

    @staticmethod
    def _scalar(value: Any) -> str:
        return str(value).lower() if isinstance(value, bool) else str(value)

    async def invoke(
        self,
        method: str,
        path: str,
        path_parameters: dict[str, Any] | None = None,
        query_parameters: dict[str, Any] | None = None,
        header_parameters: dict[str, Any] | None = None,
        body: Any = None,
    ) -> dict[str, Any]:
        operation = self.registry.get(method, path)
        if operation.method not in READ_METHODS and not self.config.allow_writes:
            raise ValueError("Write operations require OSEON_ALLOW_WRITES=true")
        path_parameters = path_parameters or {}
        query_parameters = query_parameters or {}
        header_parameters = header_parameters or {}
        self.registry.validate_parameters(operation, "path", path_parameters)
        self.registry.validate_parameters(operation, "query", query_parameters)
        protected = {
            "authorization",
            "host",
            "cookie",
            "content-length",
            "transfer-encoding",
            "connection",
            "proxy-authorization",
            "content-type",
            "api-version",
        }
        if any(name.lower() in protected for name in header_parameters):
            raise ValueError(
                "Transport and authentication headers cannot be supplied by tools"
            )
        headers = {"Accept": "application/json", "api-version": self.config.api_version}
        defaults = {
            "Trumpf-User": self.config.user_header,
            "Trumpf-Terminal": self.config.terminal_header,
        }
        declared_headers = {
            p["name"] for p in operation.parameters if p["in"] == "header"
        }
        supplied_headers = {
            k: v for k, v in defaults.items() if v and k in declared_headers
        }
        supplied_headers.update(header_parameters)
        self.registry.validate_parameters(operation, "header", supplied_headers)
        for name, value in supplied_headers.items():
            value = self._scalar(value)
            if (
                not name.isascii()
                or not name.replace("-", "").isalnum()
                or any(ord(c) < 32 or ord(c) > 126 for c in value)
            ):
                raise ValueError("Invalid HTTP header")
            headers[name] = value
        if self.config.authorization:
            headers["Authorization"] = self.config.authorization
        elif self.config.username:
            encoded = base64.b64encode(
                f"{self.config.username}:{self.config.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {encoded}"
        target = operation.path
        for name, value in path_parameters.items():
            value = self._scalar(value)
            if value in {"", ".", ".."}:
                raise ValueError("Unsafe path parameter")
            target = target.replace("{" + name + "}", quote(value, safe=""))
        query: list[tuple[str, str]] = []
        for parameter in operation.parameters:
            name = parameter["name"]
            if parameter["in"] != "query" or name not in query_parameters:
                continue
            value = query_parameters[name]
            if isinstance(value, list):
                fmt = parameter.get("collectionFormat", "csv")
                values = [self._scalar(item) for item in value]
                if fmt == "multi":
                    query.extend((name, item) for item in values)
                else:
                    separators = {"csv": ",", "ssv": " ", "tsv": "\t", "pipes": "|"}
                    if fmt not in separators:
                        raise ValueError("Unsupported array serialization")
                    query.append((name, separators[fmt].join(values)))
            else:
                query.append((name, self._scalar(value)))
        bodies = [p for p in operation.parameters if p["in"] == "body"]
        kwargs: dict[str, Any] = {}
        if not bodies and body is not None:
            raise ValueError("Operation does not declare a request body")
        if bodies:
            parameter = bodies[0]
            if body is None and parameter.get("required"):
                raise ValueError("Missing required request body")
            if body is not None:
                self.registry.validate(body, parameter["schema"])
                consumes = operation.definition.get(
                    "consumes", self.registry.document.get("consumes", [])
                )
                if "application/json" in consumes or not consumes:
                    kwargs["json"] = body
                elif "text/plain" in consumes and isinstance(body, str):
                    headers["Content-Type"] = "text/plain"
                    kwargs["content"] = body.encode()
                else:
                    raise ValueError("Unsupported request media type")
        url = self.config.base_url.rstrip("/") + self.registry.base_path + target
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=self.config.timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.request(
                    operation.method,
                    url,
                    params=tuple(query),
                    headers=headers,
                    **kwargs,
                )
        except httpx.HTTPError:
            raise ValueError(
                "Oseon transport failed; no automatic retry. A write outcome may be unknown."
            ) from None
        if not 200 <= response.status_code < 300:
            raise ValueError(
                f"Oseon returned HTTP {response.status_code}; no automatic retry. "
                "A write outcome may be unknown."
            ) from None
        if not response.content:
            return {"status": response.status_code, "data": None}
        content_type = response.headers.get("content-type", "").split(";")[0].lower()
        if (
            content_type == "application/json"
            or content_type.endswith("+json")
            or content_type == "text/json"
        ):
            try:
                return {"status": response.status_code, "data": response.json()}
            except ValueError:
                raise ValueError("Oseon returned invalid JSON") from None
        if content_type.startswith("text/"):
            return {"status": response.status_code, "data": response.text}
        return {
            "status": response.status_code,
            "content_type": content_type,
            "encoding": "base64",
            "data": base64.b64encode(response.content).decode(),
        }
