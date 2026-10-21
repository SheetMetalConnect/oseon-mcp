# Testing and contribution

Install the locked development dependencies:

```sh
uv sync --locked --extra dev
uv run --locked pytest -q
```

The default suite uses synthetic API documents and mock HTTP transports. A socket guard rejects network connections in the test process. Stdio tests launch the production entry point to discover and call tools, plus a separate synthetic server with a mock transport to prove successful HTTP dispatch over stdio. No test contacts Oseon.

Optional private-file tests are skipped unless `OSEON_TEST_API_FILE` is set to an external local API file. They construct synthetic inputs and response payloads from the selected contract without saving them. Every registered method/path pair and declared successful status is dispatched through a mock transport; default mutation blocking is checked before HTTP. A separate real stdio subprocess discovers, describes and mock-invokes every operation through SDK v2. These tests use synthetic Basic credentials, never installation credentials. HTTP request logging is suppressed, and unexpected stdio test output fails without printing its contents. Set `OSEON_EXPECTED_OPERATIONS` to assert a known operation count.

```sh
uv run --locked pytest -q -s tests/test_local_api.py
```

The optional tests print aggregate method, response-case and stdio operation counts only. Never commit vendor documentation, copied schemas, full endpoint catalogs, client payloads, configuration values or private test-session reports. Tests and fixtures committed here must remain synthetic.

Source distributions include the shared test fixtures, setup and usage docs, and README banner. After extracting a source distribution, install its locked development dependencies and run the same offline suite from that extracted directory.

Format edited Python files with Black. Build locally with `uv build --no-sources`. Changes include applicable offline tests, usage documentation and changelog entries. GitHub Actions are not used; PRs state local commands, results and verification limits. See [MIT terms](LICENSE).
