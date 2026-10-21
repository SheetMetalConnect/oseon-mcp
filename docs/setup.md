# Install and configure

Requires Python 3.10+, uv, an MCP host with stdio support, and a legally obtained local Oseon API v2 Swagger 2.0 JSON file. No vendor specification is bundled. OpenAPI 3 documents and external schema references are not supported.

```sh
uv sync --locked
```

Supply the variables below through the server process environment using your verified local secret source. The server never discovers or reads `.env` files. Keep credentials and the vendor file outside Git. Use an absolute path for `OSEON_API_FILE`, outside this checkout. The origin in `OSEON_BASE_URL` must contain only scheme, host and optional port; API paths and the optional Swagger `basePath` come from the selected file.

| Variable | Meaning |
|---|---|
| `OSEON_API_FILE` | Required user-supplied local Swagger JSON path |
| `OSEON_BASE_URL` | Required HTTP(S) origin, without credentials, path, query or fragment |
| `OSEON_AUTHORIZATION` | Complete Authorization header, as required by the installation |
| `OSEON_USERNAME`, `OSEON_PASSWORD` | Alternative Basic authentication; configure both or neither |
| `OSEON_USER_HEADER`, `OSEON_TERMINAL_HEADER` | Optional booking headers, sent only where declared in the selected operation |
| `OSEON_API_VERSION` | API version header; default `2.0`; validated against its schema where declared |
| `OSEON_ALLOW_WRITES` | Default `false`; only `true` enables mutation methods |
| `OSEON_TIMEOUT` | Positive finite HTTP timeout in seconds; default `30` |

Configure either the Authorization header or Basic credentials. The configured authentication must satisfy the selected operation’s effective security requirement before HTTP. A declared Basic requirement accepts configured Basic credentials or a complete Basic Authorization header; a declared OAuth2 requirement accepts an externally obtained Bearer token. The adapter does not acquire tokens or prove their permissions. Operation security overrides the document default, including anonymous alternatives. No credential is taken from the API file. Supply secret values literally, preserving `#`, `!`, `@`, `$` and `=`. Neither the server nor its launcher decrypts files, expands secret values or chooses a secret source. Do not put credentials in command arguments.

## Claude Desktop

From the installed checkout, obtain the local executable and checkout paths:

```sh
command -v uv
pwd
```

In Claude Desktop's Developer settings, open its local MCP configuration. Retain existing entries and add an `oseon` entry under `mcpServers`:

- Set `command` to the executable path reported by `command -v uv`.
- Set `args` to an array containing `--directory`, the checkout path reported by `pwd`, `run`, `--locked`, `python`, `-m`, and `trumpf_oseon_mcp`, in that order.
- Set `OSEON_ALLOW_WRITES` to `false` in the entry's `env` object.

See the [official local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers) for the host's configuration format.

The launched process must receive the required variables from the machine's verified secret configuration. Desktop applications do not necessarily inherit a terminal's environment. Verify variable presence without displaying their values, then restart the host to reload its local server.

## Claude Code

Run this from the installed checkout to register the same foreground command in user scope. The required Oseon variables must already be present in the Claude Code process environment. The command stores no credentials and creates no project configuration file. See the [official Claude Code MCP guide](https://code.claude.com/docs/en/mcp).

```sh
claude mcp add --transport stdio --scope user oseon -- \
  "$(command -v uv)" --directory "$PWD" run --locked \
  python -m trumpf_oseon_mcp
```

Both hosts launch a local process and own its stdin, stdout and lifetime. No listening port or remote connector is used. The server supports protocol `2026-07-28` and legacy clients through SDK v2; see the [official SDK migration guide](https://py.sdk.modelcontextprotocol.io/migration/).

For a local terminal check in the configured checkout:

```sh
./scripts/launch_mcp.sh
```

The launcher inherits the process environment and sets only the working directory. Offline verification requires no Oseon configuration:

```sh
uv run --locked --extra dev pytest -q
```

Claude Desktop and Claude Code use local stdio processes. This setup does not install a remote MCP service for Claude's web application.

## Safety and recovery

Use a server-side read-only account alongside the default write gate. GET, HEAD and OPTIONS are allowed by default; POST, PUT, PATCH, DELETE and TRACE require explicit startup opt-in. Changing configuration requires restarting the MCP process. Requests are never retried automatically. After a lost write response or server failure, reconcile actual vendor state before issuing another mutation.

Redirects and environment proxy inheritance are disabled. Only the configured origin is contacted; tools cannot change the origin or supply Authorization, Host or transport headers. HTTP errors expose status codes without response bodies, request URLs or credentials.

If startup reports invalid configuration, check the local file's readability, Swagger format and required configuration. For authentication failures, verify the configured authentication mechanism locally without pasting credentials into an issue. The server does not make a health request at startup.

API metadata, schemas and returned manufacturing data are exposed to the connected MCP host. Its model provider may receive them; running the adapter locally does not keep tool results on the local network.
