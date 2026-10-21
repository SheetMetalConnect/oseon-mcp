# Implementation reference

The current stdio surface is defined in [`__main__.py`](src/trumpf_oseon_mcp/__main__.py).

| Source | Responsibility |
|---|---|
| [`config.py`](src/trumpf_oseon_mcp/config.py) | Startup environment, origin validation and explicit write opt-in |
| [`registry.py`](src/trumpf_oseon_mcp/registry.py) | Runtime method/path identities, local references without external retrieval, discovery and input validation |
| [`api/client.py`](src/trumpf_oseon_mcp/api/client.py) | Encoded request construction, authentication, one HTTP attempt and response decoding |
| [`workflows.py`](src/trumpf_oseon_mcp/workflows.py) | Read-only work order, nesting, stock and remainder-sheet queries |
| [`tests/`](tests/) | Synthetic, network-blocked tests and optional private-file mock coverage |

`create_server` loads the selected API file once and registers three generic tools plus four read-only workflows. Duplicate vendor operation IDs remain separate because the registry key is the method/path pair. Discovery and description perform no HTTP. Invocation validates inputs and applies the write gate before constructing a request to the configured origin.

Installation and recovery are owned by [setup](docs/setup.md); the request and response contract is in [usage](docs/usage.md).
