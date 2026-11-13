"""CLI onboarding tests never read the developer's .env or call live Feishu."""

import sys
from types import SimpleNamespace

import pytest

from feishu_bitable_mcp import server


@pytest.fixture
def isolated_cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in [
        "FEISHU_APP_ID", "FEISHU_APP_SECRET", "MCP_AUTH_TOKEN", "FEISHU_ENABLE_WRITES",
        "FEISHU_READ_TABLE_URLS", "FEISHU_WRITE_TABLE_URLS", "MCP_OAUTH_ISSUER",
        "MCP_OAUTH_JWKS_URL", "MCP_PUBLIC_URL", "MCP_HOST", "MCP_PORT",
        "MCP_GITHUB_CLIENT_ID", "MCP_GITHUB_CLIENT_SECRET", "MCP_GITHUB_ALLOWED_USER_IDS",
    ]:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch, tmp_path


def test_explicit_config_works_outside_project_and_env_takes_priority(isolated_cli):
    patch, directory = isolated_cli
    config = directory / "settings.env"
    config.write_text("FEISHU_APP_ID=file-app\nFEISHU_APP_SECRET=file-secret\n")
    patch.setenv("FEISHU_APP_ID", "environment-app")
    captured = []

    def build(settings):
        captured.append(settings)
        return SimpleNamespace(run=lambda **kwargs: captured.append(kwargs))

    patch.setattr(server, "build_server", build)
    patch.setattr(sys, "argv", ["mcp", "--env-file", str(config), "--transport", "stdio"])
    server.main()
    assert captured[0].app_id == "environment-app"
    assert captured[0].app_secret == "file-secret"
    assert captured[1]["transport"] == "stdio"


def test_missing_explicit_config_fails_without_printing_path(isolated_cli, capsys):
    patch, directory = isolated_cli
    patch.setattr(sys, "argv", ["mcp", "--env-file", str(directory / "private-value.env")])
    with pytest.raises(SystemExit) as error:
        server.main()
    assert error.value.code == 2
    assert "private-value" not in capsys.readouterr().err


def test_invalid_port_does_not_echo_environment(isolated_cli, capsys):
    patch, _ = isolated_cli
    patch.setenv("FEISHU_APP_ID", "fictional-app")
    patch.setenv("FEISHU_APP_SECRET", "fictional-secret")
    patch.setenv("MCP_PORT", "private-invalid-value")
    patch.setattr(sys, "argv", ["mcp"])
    with pytest.raises(SystemExit):
        server.main()
    message = capsys.readouterr().err
    assert "MCP_PORT" in message and "private-invalid-value" not in message


def test_doctor_without_url_never_calls_feishu(isolated_cli, capsys):
    patch, _ = isolated_cli
    patch.setenv("FEISHU_APP_ID", "fictional-app")
    patch.setenv("FEISHU_APP_SECRET", "fictional-secret")
    patch.setattr(sys, "argv", ["mcp", "--doctor"])
    with pytest.raises(SystemExit) as error:
        server.main()
    assert error.value.code == 0
    assert '"live_reads": false' in capsys.readouterr().out
