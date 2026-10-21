import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from trumpf_oseon_mcp.__main__ import main
from trumpf_oseon_mcp.config import Config


def test_every_packaged_module_imports_without_configuration():
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("OSEON_")
    }
    env["OSEON_ALLOW_WRITES"] = "invalid-synthetic-value"
    script = """
import importlib
import pkgutil
import socket
import trumpf_oseon_mcp
def denied(*args, **kwargs):
    raise AssertionError("Package import attempted network access")
socket.socket.connect = denied
for module in pkgutil.walk_packages(trumpf_oseon_mcp.__path__, "trumpf_oseon_mcp."):
    importlib.import_module(module.name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


def clear_configuration(monkeypatch):
    for name in os.environ:
        if name.startswith("OSEON_"):
            monkeypatch.delenv(name)


def test_startup_ignores_local_and_parent_env_files(monkeypatch, tmp_path, api_file):
    clear_configuration(monkeypatch)
    text = f"OSEON_API_FILE={api_file}\nOSEON_BASE_URL=https://synthetic.invalid\n"
    (tmp_path / ".env").write_text(text)
    startup = tmp_path / "arbitrary-working-directory"
    startup.mkdir()
    (startup / ".env").write_text(text)
    monkeypatch.chdir(startup)
    with pytest.raises(SystemExit) as error:
        main()
    assert str(error.value) == (
        "Invalid configuration or local API file; check the setup guide."
    )


def test_startup_uses_literal_process_environment(monkeypatch, tmp_path, api_file):
    clear_configuration(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OSEON_ALLOW_WRITES=true\nOSEON_PASSWORD=ignored\n")
    values = {
        "OSEON_API_FILE": str(api_file),
        "OSEON_BASE_URL": "https://synthetic.invalid",
        "OSEON_USERNAME": "synthetic",
        "OSEON_PASSWORD": "literal#!@$=secret",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    observed = []

    def create_server(config):
        assert config == Config(
            api_file=str(api_file),
            base_url="https://synthetic.invalid",
            username="synthetic",
            password="literal#!@$=secret",
        )
        return SimpleNamespace(run=lambda **kwargs: observed.append(kwargs))

    entrypoint = importlib.import_module("trumpf_oseon_mcp.__main__")
    monkeypatch.setattr(entrypoint, "create_server", create_server)
    main()
    assert observed == [{"transport": "stdio"}]


async def test_launcher_inherits_environment_from_arbitrary_directory(
    tmp_path, api_file
):
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("OSEON_")
    }
    env.update(
        OSEON_API_FILE=str(api_file),
        OSEON_BASE_URL="https://synthetic.invalid",
        OSEON_ALLOW_WRITES="false",
    )
    (tmp_path / ".env").write_text("OSEON_API_FILE=ignored\nOSEON_ALLOW_WRITES=true\n")
    launcher = Path(__file__).resolve().parents[1] / "scripts" / "launch_mcp.sh"
    params = StdioServerParameters(
        command="bash", args=[str(launcher)], env=env, cwd=tmp_path
    )
    async with Client(params, read_timeout_seconds=10) as client:
        result = await client.call_tool("discover_operations", {})
        assert result.structured_content["total"] == 12
        blocked = await client.call_tool(
            "invoke_operation", {"method": "DELETE", "path": "/writes"}
        )
        assert blocked.is_error
        assert "OSEON_ALLOW_WRITES" in blocked.content[0].text
