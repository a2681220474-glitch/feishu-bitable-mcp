"""Small Feishu OpenAPI client with bounded reads and no automatic write retries."""

from __future__ import annotations

import asyncio
import math
import random
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .config import BitableError, Settings, Target

API_ROOT = "https://open.feishu.cn/open-apis"
TOKEN_ROUTE = "/auth/v3/tenant_access_token/internal"
EXPIRED_TOKEN_CODES = {99991663, 99991668}
ATTEMPT_TIMEOUT = 20
FIELD_TYPES = {
    1: "Text",
    2: "Number",
    3: "SingleSelect",
    4: "MultiSelect",
    5: "DateTime",
    7: "Checkbox",
    11: "Person",
    13: "Phone",
    15: "URL",
    17: "Attachment",
    18: "SingleLink",
    19: "Lookup",
    20: "Formula",
    21: "DuplexLink",
    22: "Location",
    23: "GroupChat",
    1001: "CreatedTime",
    1002: "ModifiedTime",
    1003: "CreatedBy",
    1004: "ModifiedBy",
    1005: "AutoNumber",
}


def describe_field(raw: dict[str, Any]) -> dict[str, Any]:
    """Preserve the entire API field, including unknown future properties."""
    return {**raw, "field_type_name": FIELD_TYPES.get(raw.get("type"), "Unknown")}


class FeishuClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._http = httpx.AsyncClient(
            base_url=API_ROOT,
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=False,
            transport=transport,
        )
        self._token = ""
        self._expires = 0.0
        self._token_lock = asyncio.Lock()
        self._requests = asyncio.Semaphore(4)

    async def close(self) -> None:
        await self._http.aclose()

    def _safe_message(self, value: Any, *, request_tokens: tuple[str, ...] = ()) -> str:
        message = value if isinstance(value, str) else "Unspecified upstream error"
        secrets = {
            self.settings.app_secret,
            self.settings.auth_token,
            self.settings.github_client_secret,
            self._token,
            *request_tokens,
        }
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                message = message.replace(secret, "[redacted]")
        message = re.sub(r"(?i)Bearer\s+\S+", "Bearer [redacted]", message)
        message = re.sub(
            r"(?i)((?:app_secret|(?:tenant|user)_access_token|refresh_token)[\s\"\x27:=]+)[^\s,}\"\x27]+",
            r"\1[redacted]",
            message,
        )
        return message[:500].replace("\n", " ").replace("\r", " ")

    def _payload(self, response: httpx.Response, context: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            raise BitableError(
                f"{context}: HTTP {response.status_code}; invalid JSON response."
            ) from None
        if not isinstance(payload, dict):
            raise BitableError(f"{context}: HTTP {response.status_code}; invalid response object.")
        return payload

    def _raise_api(
        self,
        response: httpx.Response,
        payload: dict[str, Any],
        context: str,
        *,
        request_tokens: tuple[str, ...] = (),
    ) -> None:
        code = payload.get("code")
        if not response.is_success or code != 0:
            safe_code = code if type(code) is int else "unknown"
            msg = self._safe_message(payload.get("msg"), request_tokens=request_tokens)
            raise BitableError(
                f"{context}: HTTP {response.status_code}; code={safe_code}; msg={msg}"
            )

    async def _send(self, method: str, route: str, **kwargs: Any) -> httpx.Response:
        # Retry only GET. POST may have succeeded even when the response was lost.
        for attempt in range(3 if method == "GET" else 1):
            try:
                async with asyncio.timeout(ATTEMPT_TIMEOUT), self._requests:
                    response = await self._http.request(method, route, **kwargs)
            except (httpx.HTTPError, TimeoutError) as exc:
                if (
                    method == "GET" and attempt < 2
                    and isinstance(exc, (httpx.TransportError, TimeoutError))
                ):
                    await asyncio.sleep(random.uniform(0.1, 0.25) * 2**attempt)
                    continue
                detail = (
                    " Write outcome is unknown; inspect records before retrying."
                    if method == "POST" and route != TOKEN_ROUTE
                    else ""
                )
                message = (
                    "Feishu request timed out."
                    if isinstance(exc, (httpx.TimeoutException, TimeoutError))
                    else "Feishu network request failed."
                )
                raise BitableError(message + detail) from None
            if (
                method != "GET"
                or response.status_code not in {429, 500, 502, 503, 504}
                or attempt == 2
            ):
                return response
            delay = random.uniform(0.1, 0.25) * 2**attempt
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    try:
                        wait = parsedate_to_datetime(retry_after).timestamp() - time.time()
                    except (ValueError, TypeError, OverflowError):
                        wait = 0.0
                if math.isfinite(wait):
                    if wait > 5:
                        # Do not retry earlier than instructed or exceed the tool budget.
                        return response
                    delay = max(delay, wait)
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def token(self) -> str:
        async with self._token_lock:
            if self._token and time.monotonic() < self._expires:
                return self._token
            response = await self._send(
                "POST",
                TOKEN_ROUTE,
                json={
                    "app_id": self.settings.app_id,
                    "app_secret": self.settings.app_secret,
                },
            )
            payload = self._payload(response, "Tenant authentication failed")
            self._raise_api(response, payload, "Tenant authentication failed")
            token = payload.get("tenant_access_token")
            expiry = payload.get("expire")
            if not isinstance(token, str) or not token or type(expiry) is not int or expiry <= 0:
                raise BitableError(
                    "Tenant authentication failed: missing token or positive expiry."
                )
            self._token = token
            self._expires = time.monotonic() + max(expiry - min(120, expiry / 10), 0)
            return token

    async def request(self, method: str, route: str, **kwargs: Any) -> dict[str, Any]:
        used_token = await self.token()
        # Keep only this call's credentials, including its one optional read retry.
        # Other requests may replace the cached token before this response arrives.
        request_tokens = (used_token,)
        context = "Feishu record creation failed" if method == "POST" else "Feishu read failed"
        response = await self._send(
            method, route, headers={"Authorization": f"Bearer {used_token}"}, **kwargs
        )
        try:
            payload = self._payload(response, context)
        except BitableError as exc:
            if method == "POST":
                raise BitableError(
                    f"{exc} Write outcome is unknown; inspect records before retrying."
                ) from None
            raise
        if method == "GET" and payload.get("code") in EXPIRED_TOKEN_CODES:
            async with self._token_lock:
                if self._token == used_token:
                    self._expires = 0.0
            used_token = await self.token()
            request_tokens += (used_token,)
            response = await self._send(
                method, route, headers={"Authorization": f"Bearer {used_token}"}, **kwargs
            )
            payload = self._payload(response, context)
        if method == "POST" and response.status_code >= 500:
            context += "; write outcome may be unknown; inspect records before retrying"
        self._raise_api(response, payload, context, request_tokens=request_tokens)
        data = payload.get("data")
        if not isinstance(data, dict):
            detail = (
                " Write outcome is unknown; inspect records before retrying."
                if method == "POST"
                else ""
            )
            raise BitableError("Feishu returned an invalid data object." + detail)
        return data

    @staticmethod
    def table_route(target: Target, suffix: str = "") -> str:
        return f"/bitable/v1/apps/{target.app_token}/tables/{target.table_id}{suffix}"

    async def all_items(self, route: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        params: dict[str, Any] = {"page_size": 100}
        for _ in range(1000):
            data = await self.request("GET", route, params=params)
            page = data.get("items")
            if not isinstance(page, list) or not all(isinstance(x, dict) for x in page):
                raise BitableError("Feishu returned invalid paginated items.")
            items.extend(page)
            if not data.get("has_more"):
                return items
            next_token = data.get("page_token")
            if not isinstance(next_token, str) or not next_token or next_token in seen:
                raise BitableError("Feishu pagination did not advance; refusing an infinite loop.")
            seen.add(next_token)
            params["page_token"] = next_token
        raise BitableError("Feishu pagination exceeded the safety limit of 1000 pages.")

    async def info(self, target: Target) -> dict[str, Any]:
        self.settings.authorize(target)
        base = await self.request("GET", f"/bitable/v1/apps/{target.app_token}")
        tables = await self.all_items(f"/bitable/v1/apps/{target.app_token}/tables")
        table = next((x for x in tables if x.get("table_id") == target.table_id), None)
        if table is None:
            raise BitableError(
                "Target table was not found. Check the exact URL and app resource permissions."
            )
        return {
            **target.identifiers(),
            "base": base.get("app", base),
            "table": table,
            "table_name": table.get("name"),
        }

    async def fields(self, target: Target) -> list[dict[str, Any]]:
        self.settings.authorize(target)
        return [
            describe_field(x) for x in await self.all_items(self.table_route(target, "/fields"))
        ]

    async def records(
        self, target: Target, page_size: int, page_token: str | None = None
    ) -> dict[str, Any]:
        self.settings.authorize(target)
        if type(page_size) is not int or not 1 <= page_size <= 500:
            raise BitableError("page_size must be an integer between 1 and 500.")
        if page_token is not None and (
            not isinstance(page_token, str) or not 1 <= len(page_token) <= 4096
        ):
            raise BitableError("page_token must be a nonempty string of at most 4096 characters.")
        params: dict[str, Any] = {"page_size": page_size}
        if page_token is not None:
            params["page_token"] = page_token
        if target.view_id:
            params["view_id"] = target.view_id
        data = await self.request("GET", self.table_route(target, "/records"), params=params)
        items = data.get("items")
        if not isinstance(items, list) or not all(
            isinstance(x, dict)
            and isinstance(x.get("fields"), dict)
            and isinstance(x.get("record_id"), str)
            for x in items
        ):
            raise BitableError("Feishu returned invalid records.")
        has_more = bool(data.get("has_more"))
        next_token = data.get("page_token")
        if has_more and (
            not isinstance(next_token, str) or not next_token or next_token == page_token
        ):
            raise BitableError("Feishu record pagination did not advance.")
        return {
            **{key: value for key, value in data.items() if key != "items"},
            "records": items,
            "has_more": has_more,
            "page_token": next_token if has_more else None,
        }

    async def create(self, target: Target, fields: dict[str, Any]) -> dict[str, Any]:
        self.settings.authorize(target, write=True)
        data = await self.request(
            "POST", self.table_route(target, "/records"), json={"fields": fields}
        )
        record = data.get("record")
        if not isinstance(record, dict) or not isinstance(record.get("record_id"), str):
            raise BitableError(
                "Feishu did not return a record ID. Inspect records before retrying."
            )
        return record
