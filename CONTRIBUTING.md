# Testing and contribution

Install the locked development dependencies:

```sh
uv sync --locked --extra dev
uv run --locked pytest -q
```

The default suite uses synthetic API documents and mock HTTP transports. A socket guard rejects network connections in the test process. Stdio tests launch the production entry point to discover and call tools, plus a separate synthetic server with a mock transport to prove successful HTTP dispatch over stdio. No test contacts Oseon.

One optional private-file test is skipped unless `OSEON_TEST_API_FILE` is set to an external local API file. It constructs synthetic inputs for every registered method/path pair and dispatches each through a mock transport, including mutation methods. It never uses installation credentials. Set `OSEON_EXPECTED_OPERATIONS` to assert a known operation count.

```sh
uv run --locked pytest -q -s tests/test_local_api.py
```

The optional test prints aggregate method counts only. Never commit vendor documentation, copied schemas, full endpoint catalogs, client payloads, configuration values or private test-session reports. Tests and fixtures committed here must remain synthetic.

Format edited Python files with Black. Build locally with `uv build --no-sources`. Changes include applicable offline tests, usage documentation and changelog entries. GitHub Actions are not used; PRs state local commands, results and verification limits. See [MIT terms](LICENSE).
