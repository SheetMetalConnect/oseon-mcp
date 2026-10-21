# Use the tools

Generic operation names, methods, paths, parameters and input schemas come from the selected local file. Four read-only workflow tools use specific GET operations declared in that file. No automatic API pagination is applied.

| Tool | Input | Result |
|---|---|---|
| `discover_operations` | Optional `query`, `method`, `offset`, `limit` (1–100) | Matching operation metadata, count and next offset |
| `describe_operation` | Exact `method` and path template returned by discovery | Operation description, security requirements, inputs, response contracts and reachable schemas |
| `invoke_operation` | Exact `method`, path template, parameter dictionaries, optional `body` and `content_type` | HTTP status and response data |
| `list_work_orders` | `page` (from 0), `size` (1–100) | One API page with core production order fields and the API page counts |
| `list_nestings` | Optional `workplace_id`, `max_count` (1–100 per workplace) | Manufacturing orders for one or all listed workplaces |
| `list_stock` | Optional `article` filter | API stock rows without embedded images |
| `list_remainder_sheets` | Optional raw-sheet `filter` | Positive stock rows for matching remainder-sheet articles, with returned article counts |

The workflow tools expose source values without translating statuses. Nestings are requested per workplace; `max_count` is applied separately to each workplace. The stock and remainder-sheet tools omit embedded images. Remainder sheets are selected from `IsRemainderSheet` articles and matched to stock by exact article name with quantity above zero. The API does not declare pagination for these article and stock routes; the returned counts do not prove complete inventory coverage.

Discover jobs or raw sheets by searching the supplied operation metadata. A search matches method, path, operation ID, summary and tags; it returns only what that file declares. Use the returned method/path pair as the identity: operation IDs may be duplicated.

Describe the chosen operation before calling it. Keep placeholders in the path template and pass their values through `path_parameters`. Pass query and header values through `query_parameters` and `header_parameters`, using declared names and JSON types. A body is the declared JSON value, including an object, array or scalar where supported. Request bodies prefer declared JSON. Set `content_type` to select a declared JSON, `text/json` or plain-text representation; a plain-text body must be a string. Form and multipart input are not supported, and form fields are never inferred from a body schema. An operation with a JSON alternative remains addressable through that representation.

Required parameters, types, enums, numeric constraints, finite JSON numbers, supported JSON Schema formats, Swagger base64/integer/float bounds and body schemas are validated before HTTP. Undeclared parameters and unregistered method/path pairs are rejected. Path segments are encoded individually; array path, query and header parameters use the Swagger collection format. The Accept header follows declared response media types. No filtering, field renaming, aggregation or automatic API pagination is applied.

`describe_operation` returns the selected operation’s summary, description, tags, deprecation flag, declared security and response contracts. Its schema map includes only references reachable from that operation’s inputs and responses. These are local metadata, not evidence of installation behavior.

Security alternatives retain Swagger's OR/AND semantics. Requirements that cannot be satisfied by the single configured Authorization header are rejected before HTTP; registration and description remain available.

Responses retain their JSON structure. Empty responses return `data: null`; text responses return a string; other media return base64 data with the content type and encoding. Declared response headers are returned as strings under `headers`; credential/cookie headers are withheld. A 304 result returns `data: null` only when declared for the operation or covered by its default response. Redirects are never followed. Large responses and files are read into memory, so select narrow API filters where the supplied contract permits them.

## MCP interface

Seven tools are registered. The former 13 named order/dashboard tools are removed; legacy tool-name compatibility is not provided.

| Removed tool group | Names |
|---|---|
| Customer orders | `get_customer_orders`, `get_customer_order_details`, `search_customer_orders`, `get_customer_orders_by_status`, `get_orders_for_customer` |
| Production orders | `get_production_orders`, `search_production_orders`, `get_in_progress_production_orders`, `get_released_production_orders`, `get_finished_production_orders`, `get_overdue_production_orders` |
| Dashboards | `get_production_summary`, `get_orders_summary` |

The old Python `tools`, `models`, `utils` and exception modules are removed. Package imports do not create a server or read configuration. Construct a server with `create_server(config)` from `trumpf_oseon_mcp.__main__`; use `Config`, `OperationRegistry` and `OseonAPIClient.invoke` for programmatic dispatch. The [example](../examples/basic_usage.py) performs local discovery without HTTP.

Local-file mock coverage proves registration and request construction. It does not establish that every documented operation exists on an installation, that credentials authorize it, or that an accepted mutation produces its intended business effect.
