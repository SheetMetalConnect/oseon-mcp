"""Runtime Swagger operation registry; no vendor catalog is bundled."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft4Validator, FormatChecker

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
        if document.get("swagger") != "2.0":
            raise ValueError("A Swagger 2.0 API document is required")
        self.document = document
        self._check_refs(document)
        self.base_path = document.get("basePath", "").rstrip("/")
        self._check_path(self.base_path or "/")
        self.operations: dict[tuple[str, str], Operation] = {}
        for path, item in document["paths"].items():
            self._check_path(path)
            for method, definition in item.items():
                if method not in METHODS:
                    continue
                parameters = {}
                for parameter in item.get("parameters", []) + definition.get(
                    "parameters", []
                ):
                    parameter = self.resolve(parameter)
                    if parameter["in"] not in {"path", "query", "header", "body"}:
                        raise ValueError(
                            "Unsupported parameter location in API document"
                        )
                    parameters[(parameter["in"], parameter["name"])] = parameter
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
            if "$ref" in value and not value["$ref"].startswith("#/"):
                raise ValueError("Only local API references are supported")
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
                raise ValueError("Cyclic parameter reference")
            seen.add(ref)
            value = self.document
            for part in ref[2:].split("/"):
                value = value[part.replace("~1", "/").replace("~0", "~")]
        return value

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
        # Return only local definitions reachable from this operation.
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

        collect(operation.parameters)
        return {
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
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("Input must be JSON with finite numbers") from None
        root = {**self.document, **schema}
        validator = Draft4Validator(root, format_checker=FormatChecker())
        if next(validator.iter_errors(value), None) is not None:
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
