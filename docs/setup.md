# Install and configure

Requires Python 3.10+, uv, an MCP host with stdio support, and a legally obtained local Oseon API v2 Swagger 2.0 JSON file. No vendor specification is bundled. OpenAPI 3 documents and external schema references are not supported.

```sh
uv sync --locked
cp env.example .env
```

Fill `.env` locally. Do not add it or the vendor file to Git. Use an absolute path for `OSEON_API_FILE`, preferably outside this checkout. The origin in `OSEON_BASE_URL` must contain only scheme, host and optional port; API paths and the optional Swagger `basePath` come from the selected file.

| Variable | Meaning |
|---|---|
| `OSEON_API_FILE` | Required user-supplied local Swagger JSON path |
| `OSEON_BASE_URL` | Required HTTP(S) origin, without credentials, path, query or fragment |
| `OSEON_AUTHORIZATION` | Complete Authorization header, as required by the installation |
| `OSEON_USERNAME`, `OSEON_PASSWORD` | Alternative Basic authentication; configure both or neither |
| `OSEON_USER_HEADER`, `OSEON_TERMINAL_HEADER` | Optional booking headers, sent only where declared in the selected operation |
| `OSEON_API_VERSION` | API version header; default `2.0` |
| `OSEON_ALLOW_WRITES` | Default `false`; only `true` enables mutation methods |
| `OSEON_TIMEOUT` | Positive finite HTTP timeout in seconds; default `30` |

Configure either the Authorization header or Basic credentials. No authentication is inferred from a vendor file. Secrets containing `#`, `!`, `@`, `$` or `=` must be preserved as literal values; quote them in `.env` as needed. The server loads `.env` from its startup directory; explicit process environment values take precedence.

## Connect an MCP host

Configure the host to launch `uv` with arguments `run`, `--directory`, `${CHECKOUT_PATH}`, `--locked`, `python`, `-m`, `trumpf_oseon_mcp`. Replace `${CHECKOUT_PATH}` with the checkout's absolute path. Provide the configuration variables through the host's environment settings, or launch with the checkout as its working directory to load `.env`.

For a terminal session in the configured checkout:

```sh
uv run --locked python -m trumpf_oseon_mcp
```

The process is a foreground stdio server: the MCP host owns its stdin, stdout and lifetime. It does not open a listening port. It supports protocol `2026-07-28` and legacy clients through SDK v2; see the [official migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md).

## Safety and recovery

Use a server-side read-only account alongside the default write gate. GET, HEAD and OPTIONS are allowed by default; POST, PUT, PATCH, DELETE and TRACE require explicit startup opt-in. Changing configuration requires restarting the MCP process. Requests are never retried automatically. After a lost write response or server failure, reconcile actual vendor state before issuing another mutation.

Redirects and environment proxy inheritance are disabled. Only the configured origin is contacted; tools cannot change the origin or supply Authorization, Host or transport headers. HTTP errors expose status codes without response bodies, request URLs or credentials.

If startup reports invalid configuration, check the local file's readability, Swagger format and required configuration. For authentication failures, verify the configured authentication mechanism locally without pasting credentials into an issue. The server does not make a health request at startup.

API metadata, schemas and returned manufacturing data are exposed to the connected MCP host. Its model provider may receive them; running the adapter locally does not keep tool results on the local network.
