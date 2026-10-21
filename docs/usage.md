# Use the tools

All operation names, methods, paths, parameters and input schemas come from the selected local file. The adapter contains no endpoint catalog and makes no assumptions about job labels, raw-sheet fields, sorting, status meanings or server pagination.

| Tool | Input | Result |
|---|---|---|
| `discover_operations` | Optional `query`, `method`, `offset`, `limit` (1–100) | Matching operation metadata, count and next offset |
| `describe_operation` | Exact `method` and path template returned by discovery | Declared inputs, media types and reachable input schemas |
| `invoke_operation` | Exact `method`, path template, parameter dictionaries and optional `body` | HTTP status and response data |

Discover jobs or raw sheets by searching the supplied operation metadata. A search matches method, path, operation ID, summary and tags; it returns only what that file declares. Use the returned method/path pair as the identity: operation IDs may be duplicated.

Describe the chosen operation before calling it. Keep placeholders in the path template and pass their values through `path_parameters`. Pass query and header values through `query_parameters` and `header_parameters`, using declared names and JSON types. A body is the declared JSON value, including an object, array or scalar where supported. Request bodies use JSON or declared plain text. Form and multipart input are not supported.

Required parameters, types, enums, numeric constraints, finite JSON numbers, supported JSON Schema formats and body schemas are validated before HTTP. Undeclared parameters and unregistered method/path pairs are rejected. Path segments are encoded individually; array path, query and header parameters use the Swagger collection format. The Accept header follows declared response media types. No filtering, field renaming, aggregation or automatic API pagination is applied.

Responses retain their JSON structure. Empty responses return `data: null`; text responses return a string; other media return base64 data with the content type and encoding. Large responses and files are read into memory, so select narrow API filters where the supplied contract permits them.

## Migration

The previous order-specific MCP tools, dashboard names, default sorting, recent-date filters and automatic pagination are replaced by these three generic tools. Package imports no longer create a server or read configuration. Construct a server with `create_server(config)` from `trumpf_oseon_mcp.__main__`; use `Config`, `OperationRegistry` and `OseonAPIClient.invoke` for programmatic dispatch. The [example](../examples/basic_usage.py) performs local discovery without HTTP.

Local-file mock coverage proves registration and request construction. It does not establish that every documented operation exists on an installation, that credentials authorize it, or that an accepted mutation produces its intended business effect.
