<p align="center"><img src="docs/assets/banner.svg" alt="Oseon MCP" width="100%"></p>

# Oseon MCP

Inspect Oseon order and material information with an MCP agent using the operations declared in your local API file. The server uses MCP Python SDK v2 and starts in read-only mode.

**Use at your own risk. This educational software carries no warranty. Write access can change manufacturing data.**

Related software: [🔌 Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) provides the server and client protocol implementation.

```mermaid
flowchart LR
    F[Local API file] --> R[Operation registry]
    H[MCP host] --> S[Stdio server]
    S --> R
    S --> V[Validation and write gate]
    V --> A[Configured Oseon API]
    A --> S
    S --> H
```

## What you can ask

- **Customer orders:** “Show the details of a known customer order.”
- **Production orders:** “Show the details of a known production order.”
- **Raw sheets and stock:** “Show material information for a known raw sheet or stock item.”

These activities use declared GET operations with the required identifiers. The agent discovers the matching operations, describes their inputs and responses, then invokes the selected operation. See the [tool usage guide](docs/usage.md).

## Scope

API/MCP parity means support for the declared REST method/path operations in the supplied Swagger 2.0 file, within the documented input and media rules. It does not establish installation-specific availability, permissions or live business outcomes. Mutations require explicit startup opt-in. A read-only SQL connection to TRUMPF systems is **out of scope** for this educational demo.

| Guide | Contents |
|---|---|
| [Install and configure](docs/setup.md) | Local API file, authentication and MCP host setup |
| [Use the tools](docs/usage.md) | Discover, describe and invoke operations |
| [Testing and contribution](CONTRIBUTING.md) | Offline tests and private-file coverage |
| [Implementation](ARCHITECTURE.md) | Source ownership and request flow |
| [Changelog](CHANGELOG.md) | Package behavior changes |

First action, from the checkout with Python 3.10+ and uv installed:

```sh
uv sync --locked
```

## About

Built by [Luke van Enkhuizen](https://vanenkhuizen.com) to demonstrate AI + manufacturing integration.

**No TRUMPF affiliation** — Educational project using public API documentation. TRUMPF owns Oseon and its API documentation; this repository does not distribute that documentation.

**MIT License** — [License terms](LICENSE) | **v2.0.0** — Runtime API registry and MCP SDK v2 adapter.
