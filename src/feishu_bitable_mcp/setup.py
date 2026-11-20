"""First-use wizard; writes a new private .env only, never overwrites credentials."""

from __future__ import annotations

import getpass
import json
import os
import warnings
from pathlib import Path

from .config import BitableError, Settings


def initialize(path: str) -> None:
    destination = Path(path)
    if destination.exists():
        raise BitableError("Configuration already exists; edit it or choose a new --env-file.")
    app_id = input("Feishu App ID: ").strip()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            secret = getpass.getpass("Feishu App Secret (hidden): ").strip()
    except getpass.GetPassWarning:
        raise BitableError("Use a secure terminal or edit a private .env manually.") from None
    public_url = input("Public HTTPS MCP URL (ending /mcp): ").strip()
    Settings(app_id, secret, identity="user", public_url=public_url)
    values = {
        "FEISHU_APP_ID": app_id, "FEISHU_APP_SECRET": secret,
        "FEISHU_AUTH_MODE": "user", "MCP_PUBLIC_URL": public_url,
        "MCP_HOST": "127.0.0.1", "MCP_PORT": "8000", "FEISHU_ENABLE_WRITES": "false",
    }
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("# Private configuration. Never commit or share this file.\n")
            for key, value in values.items():
                stream.write(f"{key}={json.dumps(value, ensure_ascii=False)}\n")
    except OSError:
        raise BitableError("Cannot create config; check its path and permissions.") from None
    print("Configuration saved. Add this redirect URL in your Feishu app security settings:")
    print(public_url.removesuffix("/mcp") + "/auth/callback")
    print("Enable the read-only scopes listed in docs/setup.md, then start the MCP service.")
