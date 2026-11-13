"""Opt-in, read-only diagnostics. Never print credentials or record content."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .auth import configured_auth
from .client import FeishuClient
from .config import BitableError, Settings, Target


async def diagnose(settings: Settings, url: str | None, api: FeishuClient) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [{"step": "configuration", "ok": True}]
    result: dict[str, Any] = {"ok": True, "checks": checks, "live_reads": bool(url)}
    if not url:
        result["next_step"] = "Run --doctor --url <test-table-url> to test Feishu access."
        return result
    step = "target"
    try:
        target = Target.parse(url)
        settings.authorize(target)
        checks.append({"step": step, "ok": True})
        async with asyncio.timeout(75):
            step = "tenant_authentication"
            await api.token()
            checks.append({"step": step, "ok": True})
            step = "base_and_table_access"
            await api.info(target)
            checks.append({"step": step, "ok": True})
            step = "fields_access"
            fields = await api.fields(target)
            checks.append({"step": step, "ok": True, "field_count": len(fields)})
            step = "records_access"
            page = await api.records(target, 1)
            checks.append({"step": step, "ok": True, "sample_count": len(page["records"])})
    except (BitableError, TimeoutError) as exc:
        result["ok"] = False
        checks.append({
            "step": step, "ok": False,
            "message": str(exc) if isinstance(exc, BitableError) else "Diagnostic timed out.",
            "next_step": (
                "Check app credentials for authentication failures; for read failures, check "
                "the URL, app API scopes and target Base resource authorization. See docs/setup.md."
            ),
        })
    return result


async def run_doctor(url: str | None) -> int:
    try:
        settings = Settings.from_env()
        configured_auth(settings)
    except (BitableError, ValueError) as exc:
        # Even invalid environment values must never be echoed to the terminal.
        print(json.dumps({"ok": False, "checks": [{
            "step": "configuration", "ok": False,
            "message": str(exc) if isinstance(exc, BitableError) else "Invalid auth settings.",
            "next_step": "See .env.example and docs/setup.md; never share secret values.",
        }]}))
        return 1
    api = FeishuClient(settings)
    try:
        result = await diagnose(settings, url, api)
    finally:
        await api.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1
