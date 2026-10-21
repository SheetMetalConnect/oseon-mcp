# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added
- Read-only MCP tools for work orders, workplace nestings, stock and remainder sheets using declared GET operations.
- Remainder-sheet results match articles to positive stock by article name and report how many raw-sheet articles the API returned.

## [2.0.0] - 2026-10-21

### Changed
- **BREAKING:** MCP SDK v2 and three generic discovery, description and invocation tools replace the previous named order/dashboard tools.
- **BREAKING:** A configured external Swagger 2.0 file and HTTP(S) origin are required. Configuration comes only from the process environment; implicit `.env` discovery is removed. Package imports do not read configuration or create a server.
- Method/path identities preserve operations with duplicate operation IDs. Description exposes declared inputs, responses, security and reachable local schemas.
- Path, query, header and body inputs follow declared schemas and collection formats. Request media negotiation supports declared JSON and plain text.
- Responses retain JSON, text, empty or base64 binary data and safe declared headers. A 304 response requires an operation declaration or default response.
- Read-only startup defaults require explicit opt-in for mutations. Security requirements are checked before HTTP; redirects, inherited proxies and automatic retries are disabled.
- Foreground stdio configuration supports local Claude Desktop and Claude Code hosts.

### Fixed
- Unresolvable and cyclic local schema references fail with sanitized errors before transport. Schema validation cannot retrieve external resources.
- Invalid origins and non-finite JSON input or response numbers are rejected without exposing values.
- Booking defaults and supplied headers match declared header names case-insensitively; duplicate spellings are rejected.
- Configured API version headers satisfy required declarations and are validated against declared schemas; tool overrides remain blocked.
- Private-file tests clear captured output and suppress original exception diagnostics before reporting failures.
- Source distributions include deterministic offline tests, fixtures, usage/setup documentation and supporting assets.

### Removed
- Unregistered order tools, inferred status models, demo redaction, business filters, pagination helpers and unused exception classes.
- The implicit dotenv dependency and obsolete environment example; the setup table owns configuration guidance.
- The live-I/O test script, background launcher, GitHub Actions workflow and internal PR preparation files.

## [1.0.0] - 2024-11-05

### Added
- Initial release
- 29 MCP tools for TRUMPF Oseon API
- Basic authentication support
- Pagination support
- Quality filtering

[2.0.0]: https://github.com/SheetMetalConnect/oseon-mcp/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/SheetMetalConnect/oseon-mcp/releases/tag/v1.0.0
