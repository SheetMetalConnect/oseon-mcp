"""Inspect local operation metadata without making an HTTP request."""

from trumpf_oseon_mcp.config import get_config
from trumpf_oseon_mcp.registry import OperationRegistry


def main() -> None:
    registry = OperationRegistry.load(get_config().api_file)
    result = registry.discover(limit=5)
    print(f"Registered operations: {result['total']}")
    for operation in result["operations"]:
        print(operation["method"], operation["path"])


if __name__ == "__main__":
    main()
