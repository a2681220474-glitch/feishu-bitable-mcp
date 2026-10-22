"""Explicit configuration and URL-derived targets; no import-time environment reads."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit


class BitableError(Exception):
    """A safe, user-facing error. Never include request headers or raw responses."""


@dataclass(frozen=True)
class Target:
    app_token: str
    table_id: str
    view_id: str | None = None

    @classmethod
    def parse(cls, url: str) -> Target:
        if (
            not isinstance(url, str)
            or len(url) > 4096
            or any(ord(c) <= 32 or ord(c) == 127 for c in url)
        ):
            raise BitableError("Use a complete HTTPS Feishu /base/ URL without whitespace.")
        try:
            parts = urlsplit(url)
            host = parts.hostname or ""
            port = parts.port
            query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=30)
        except ValueError:
            raise BitableError("Invalid Feishu Bitable URL.") from None
        path = re.fullmatch(r"/base/([A-Za-z0-9]{10,100})/?", parts.path)
        if (
            parts.scheme != "https"
            or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)*feishu\.cn", host)
            or parts.username is not None
            or parts.password is not None
            or port is not None
            or parts.fragment
            or not path
            or "\\" in url
        ):
            raise BitableError(
                "Only HTTPS feishu.cn /base/ links without ports or fragments are accepted."
            )

        def identifier(key: str, pattern: str, required: bool) -> str | None:
            values = query.get(key, [])
            if not values and not required:
                return None
            if len(values) != 1 or not re.fullmatch(pattern, values[0]):
                raise BitableError(f"URL must contain exactly one valid {key} parameter.")
            return values[0]

        table_id = identifier("table", r"tbl[A-Za-z0-9]{7,100}", True)
        view_id = identifier("view", r"vew[A-Za-z0-9]{7,100}", False)
        assert table_id is not None
        return cls(path[1], table_id, view_id)

    @property
    def key(self) -> tuple[str, str]:
        return self.app_token, self.table_id

    def identifiers(self) -> dict[str, str | None]:
        return {"app_token": self.app_token, "table_id": self.table_id, "view_id": self.view_id}


def _targets(name: str) -> frozenset[tuple[str, str]]:
    value = os.getenv(name, "")
    return frozenset(Target.parse(url.strip()).key for url in value.split(",") if url.strip())


@dataclass(frozen=True)
class Settings:
    app_id: str = field(repr=False)
    app_secret: str = field(repr=False)
    auth_token: str = field(default="", repr=False)
    enable_writes: bool = False
    read_tables: frozenset[tuple[str, str]] = frozenset()
    write_tables: frozenset[tuple[str, str]] = frozenset()

    def __post_init__(self) -> None:
        if not self.app_id or not self.app_secret:
            raise BitableError("Set FEISHU_APP_ID and FEISHU_APP_SECRET in your local .env.")
        if self.auth_token and len(self.auth_token) < 32:
            raise BitableError("MCP_AUTH_TOKEN must contain at least 32 characters.")
        if self.enable_writes and (not self.auth_token or not self.write_tables):
            raise BitableError("Writes require MCP_AUTH_TOKEN and exact FEISHU_WRITE_TABLE_URLS.")

    @classmethod
    def from_env(cls) -> Settings:
        flag = os.getenv("FEISHU_ENABLE_WRITES", "false").lower().strip()
        if flag not in {"true", "false"}:
            raise BitableError("FEISHU_ENABLE_WRITES must be true or false.")
        return cls(
            app_id=os.getenv("FEISHU_APP_ID", "").strip(),
            app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
            auth_token=os.getenv("MCP_AUTH_TOKEN", "").strip(),
            enable_writes=flag == "true",
            read_tables=_targets("FEISHU_READ_TABLE_URLS"),
            write_tables=_targets("FEISHU_WRITE_TABLE_URLS"),
        )

    def authorize(self, target: Target, *, write: bool = False) -> None:
        if self.read_tables and target.key not in self.read_tables:
            raise BitableError("This table is not in FEISHU_READ_TABLE_URLS.")
        if write and (not self.enable_writes or target.key not in self.write_tables):
            raise BitableError("Record creation is disabled or this table is not write-authorized.")
