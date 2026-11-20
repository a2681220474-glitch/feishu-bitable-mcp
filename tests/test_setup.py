"""Private setup must never overwrite credentials or print a secret."""

import os
import stat

import pytest
from dotenv import dotenv_values

from feishu_bitable_mcp.config import BitableError
from feishu_bitable_mcp.setup import initialize


def test_setup_creates_private_config_without_echoing_secret(monkeypatch, tmp_path, capsys):
    inputs = iter(["fictional-app", "https://mcp.example.com/mcp"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    secret = 'fictional-secret-${SHOULD_NOT_EXPAND}'
    monkeypatch.setattr("getpass.getpass", lambda _: secret)
    target = tmp_path / "settings.env"
    initialize(str(target))
    config = dotenv_values(target, interpolate=False)
    assert config["FEISHU_APP_SECRET"] == secret
    assert config["FEISHU_AUTH_MODE"] == "user"
    assert secret not in capsys.readouterr().out
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(BitableError, match="already exists"):
        initialize(str(target))
    assert dotenv_values(target, interpolate=False)["FEISHU_APP_SECRET"] == secret
