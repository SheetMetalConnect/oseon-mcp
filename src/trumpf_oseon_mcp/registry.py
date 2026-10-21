"""Runtime Swagger operation registry; no vendor catalog is bundled."""

import base64
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft4Validator, FormatChecker
from referencing import Registry
from referencing.exceptions import Unresolvable

METHODS = frozenset(
    {"get", "head", "options", "post", "put", "patch", "delete", "trace"}
)
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    definition: dict[str, Any]
    parameters: tuple[dict[str, Any], ...]

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


class OperationRegistry:
    def __init__(self, document: dict[str, Any]):
        if (
            not isinstance(document, dict)
            or document.get("swagger") != "2.0"
            or not isinstance(document.get("paths"), dict)
        ):
            raise ValueError("A Swagger 2.0 API document with paths is required")
        self.document: dict[str, Any] = document
        self.format_checker = FormatChecker()
        for name, bits in (("int32", 32), ("int64", 64)):
            self.format_checker.checks(name)(
                lambda value, width=bits: not isinstance(value, int)
                or -(2 ** (width - 1)) <= value < 2 ** (width - 1)
            )
        for name, bound in (
            ("float", (2 - 2**-23) * 2**127),
            ("double", sys.float_info.max),
        ):
            self.format_checker.checks(name)(
                lambda value, maximum=bound: not isinstance(value, (int, float))
                or abs(value) <= maximum
            )
        self.format_checker.checks("byte")(self._base64_string)
        self._check_refs(document)
        self.base_path = document.get("basePath", "").rstrip("/")
        self._check_path(self.base_path or "/")
        self.operations: dict[tuple[str, str], Operation] = {}
        for path, item in document["paths"].items():
            self._check_path(path)
            if not isinstance(item, dict):
                raise ValueError("API path definitions must be objects")
            item = self.resolve(item)
            for method, definition in item.items():
                if method not in METHODS:
                    continue
                if not isinstance(definition, dict):
                    raise ValueError("API operation definitions must be objects")
                parameters = {}
                for parameter in item.get("parameters", []) + definition.get(
                    "parameters", []
                ):
                    parameter = self.resolve(parameter)
                    if parameter["in"] not in {"path", "query", "header", "body"}:
                        raise ValueError(
                            "Unsupported parameter location in API document"
                        )
                    name = parameter["name"]
                    if parameter["in"] == "header":
                        name = name.lower()
                    parameters[(parameter["in"], name)] = parameter
                operation = Operation(
                    method.upper(), path, definition, tuple(parameters.values())
                )
                self.operations[(operation.method, path)] = operation

    @classmethod
    def load(cls, path: str | Path) -> "OperationRegistry":
        with Path(path).open(encoding="utf-8-sig") as source:
            return cls(json.load(source))

    @staticmethod
    def _check_path(path: str) -> None:
        if (
            not path.startswith("/")
            or path.startswith("//")
            or any(c in path for c in "?#\\\r\n")
            or any(part in {".", ".."} for part in path.split("/"))
        ):
            raise ValueError("Unsafe path in API document")

    def _check_refs(self, value: Any) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                if not isinstance(value["$ref"], str) or not value["$ref"].startswith(
                    "#/"
                ):
                    raise ValueError("Only local API references are supported")
                self.resolve(value)
            for child in value.values():
                self._check_refs(child)
        elif isinstance(value, list):
            for child in value:
                self._check_refs(child)

    def resolve(self, value: dict[str, Any]) -> dict[str, Any]:
        seen = set()
        while "$ref" in value:
            ref = value["$ref"]
            if ref in seen:
                raise ValueError("Cyclic local API reference")
            seen.add(ref)
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise ValueError("Only local API references are supported")
            value = self.document
            try:
                for part in ref[2:].split("/"):
                    value = value[part.replace("~1", "/").replace("~0", "~")]
            except (KeyError, TypeError):
                raise ValueError("Unresolvable local API reference") from None
            if not isinstance(value, dict):
                raise ValueError("Local API reference must resolve to an object")
        return value

    @staticmethod
    def _base64_string(value: Any) -> bool:
        if not isinstance(value, str):
            return True
        try:
            base64.b64decode(value, validate=True)
        except ValueError:
            return False
        return True

    def validate_security(self, operation: Operation, authorization: str) -> None:
        requirements = operation.definition.get(
            "security", self.document.get("security", [])
        )
        schemes = self.document.get("securityDefinitions", {})
        if not requirements:
            return
        prefixes = {"basic": "basic", "oauth2": "bearer"}
        kind, _, credential = authorization.partition(" ")
        for alternative in requirements:
            if not alternative:
                return
            if (
                len(alternative) == 1
                and credential
                and all(
                    prefixes.get(schemes.get(name, {}).get("type")) == kind.lower()
                    for name in alternative
                )
            ):
                return
        raise ValueError(
            "Configured authentication does not satisfy operation security"
        )

    def get(self, method: str, path: str) -> Operation:
        try:
            return self.operations[(method.upper(), path)]
        except KeyError:
            raise ValueError("Method/path pair is not registered") from None

    def discover(
        self,
        query: str = "",
        method: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Use offset >= 0 and limit between 1 and 100")
        if method and method.lower() not in METHODS:
            raise ValueError("Unknown HTTP method")
        matches = []
        for operation in self.operations.values():
            definition = operation.definition
            item = {
                "method": operation.method,
                "path": operation.path,
                "operation_id": definition.get("operationId"),
                "summary": definition.get("summary", ""),
                "tags": definition.get("tags", []),
                "requires_write_opt_in": operation.method not in READ_METHODS,
            }
            if method and operation.method != method.upper():
                continue
            if query.casefold() not in json.dumps(item).casefold():
                continue
            matches.append(item)
        return {
            "total": len(matches),
            "operations": matches[offset : offset + limit],
            "next_offset": offset + limit if offset + limit < len(matches) else None,
        }

    def describe(self, method: str, path: str) -> dict[str, Any]:
        operation = self.get(method, path)
        schemas: dict[str, Any] = {}

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                ref = value.get("$ref")
                if ref and ref not in schemas:
                    schemas[ref] = self.resolve({"$ref": ref})
                    collect(schemas[ref])
                for child in value.values():
                    collect(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    collect(child)

        responses = operation.definition.get("responses", {})
        security = operation.definition.get(
            "security", self.document.get("security", [])
        )
        collect(operation.parameters)
        collect(responses)
        return {
            "operation_id": operation.definition.get("operationId"),
            "summary": operation.definition.get("summary", ""),
            "description": operation.definition.get("description", ""),
            "tags": operation.definition.get("tags", []),
            "deprecated": operation.definition.get("deprecated", False),
            "responses": responses,
            "security": security,
            "security_schemes": {
                name: self.document.get("securityDefinitions", {}).get(name, {})
                for alternative in security
                for name in alternative
            },
            "method": operation.method,
            "path": operation.path,
            "parameters": operation.parameters,
            "schemas": schemas,
            "consumes": operation.definition.get(
                "consumes", self.document.get("consumes", [])
            ),
            "produces": operation.definition.get(
                "produces", self.document.get("produces", [])
            ),
            "requires_write_opt_in": operation.method not in READ_METHODS,
        }

    def validate(self, value: Any, schema: dict[str, Any]) -> None:
        self._check_refs(schema)
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("Input must be JSON with finite numbers") from None
        root = {**self.document, **schema}
        validator = Draft4Validator(
            root, format_checker=self.format_checker, registry=Registry()
        )
        try:
            invalid = next(validator.iter_errors(value), None) is not None
        except (Unresolvable, RecursionError):
            raise ValueError("Unresolvable or cyclic local API schema") from None
        if invalid:
            raise ValueError("Value does not match the declared API schema")

    def validate_parameters(
        self, operation: Operation, location: str, values: dict[str, Any]
    ) -> None:
        declared = {p["name"]: p for p in operation.parameters if p["in"] == location}
        if values.keys() - declared.keys():
            raise ValueError(f"Undeclared {location} parameter")
        for name, parameter in declared.items():
            if name not in values:
                if parameter.get("required") or location == "path":
                    raise ValueError(f"Missing required {location} parameter")
                continue
            schema = {
                k: v
                for k, v in parameter.items()
                if k
                not in {"in", "name", "required", "description", "collectionFormat"}
            }
            self.validate(values[name], schema)
        if location == "path" and set(
            re.findall(r"\{([^{}]+)\}", operation.path)
        ) != set(values):
            raise ValueError("Path parameters do not match the registered template")
