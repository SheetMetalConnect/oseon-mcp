"""Stdio entry point for MCP SDK v2."""

import logging
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from .api.client import OseonAPIClient
from .config import Config, get_config
from .registry import OperationRegistry
from .workflows import ReadOnlyWorkflows


def create_server(
    config: Config,
    registry: OperationRegistry | None = None,
    client: OseonAPIClient | None = None,
) -> MCPServer:
    registry = (
        registry if registry is not None else OperationRegistry.load(config.api_file)
    )
    client = client if client is not None else OseonAPIClient(config, registry)
    workflows = ReadOnlyWorkflows(client)
    server = MCPServer(
        "oseon-mcp",
        version=__version__,
        log_level="WARNING",
        instructions=(
            "Discover operations from the local API file, describe their inputs, "
            "then invoke an exact method/path template. "
            "Read-only work order, nesting, stock and remainder-sheet workflows "
            "are available alongside exact API dispatch. "
            "Tool results are visible to the MCP host and its model provider."
        ),
    )

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def discover_operations(
        query: str = "", method: str | None = None, offset: int = 0, limit: int = 25
    ) -> dict[str, Any]:
        """Search local operation metadata without HTTP; results are paginated."""
        try:
            return registry.discover(query, method, offset, limit)
        except ValueError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def describe_operation(method: str, path: str) -> dict[str, Any]:
        """Read operation metadata, input schemas and declared response contracts."""
        try:
            return registry.describe(method, path)
        except ValueError as error:
            raise ToolError(str(error)) from None

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=not config.allow_writes,
            destructive_hint=config.allow_writes,
            idempotent_hint=False,
            open_world_hint=True,
        )
    )
    async def invoke_operation(
        method: str,
        path: str,
        path_parameters: dict[str, Any] | None = None,
        query_parameters: dict[str, Any] | None = None,
        header_parameters: dict[str, Any] | None = None,
        body: Any = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Invoke one operation. Writes require startup opt-in; no retries."""
        try:
            return await client.invoke(
                method,
                path,
                path_parameters,
                query_parameters,
                header_parameters,
                body,
                content_type,
            )
        except ValueError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    async def list_work_orders(page: int = 0, size: int = 20) -> dict[str, Any]:
        """List one API page of production work orders with core fields."""
        try:
            return await workflows.work_orders(page, size)
        except ValueError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    async def list_nestings(
        workplace_id: int | None = None, max_count: int = 20
    ) -> dict[str, Any]:
        """List manufacturing nestings for one or all known workplaces."""
        try:
            return await workflows.nestings(workplace_id, max_count)
        except ValueError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    async def list_stock(article: str = "") -> list[dict[str, Any]]:
        """List stock rows, optionally filtered by article text."""
        try:
            return await workflows.stock(article)
        except ValueError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    async def list_remainder_sheets(filter: str = "") -> dict[str, Any]:
        """Find remainder sheets with positive stock; API lists may be limited."""
        try:
            return await workflows.remainder_sheets(filter)
        except ValueError as error:
            raise ToolError(str(error)) from None

    return server


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    try:
        server = create_server(get_config())
    except (ValueError, KeyError, OSError):
        raise SystemExit(
            "Invalid configuration or local API file; check the setup guide."
        ) from None
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
