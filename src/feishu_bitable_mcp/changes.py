"""Preview-bound, actor-bound, durable single-dispatch mutation coordination."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

from .change_policy import authorize, target_key
from .change_store import ChangeStore
from .config import BitableError, Target


def fingerprint(value: Any) -> str:
    try:
        body = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, UnicodeError):
        raise BitableError("Change content must be finite JSON data.") from None
    try:
        encoded = body.encode()
    except UnicodeError:
        raise BitableError("Change content must contain valid Unicode text.") from None
    if len(encoded) > 500_000:
        raise BitableError("Change payload exceeds 500000 bytes.")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class Plan:
    owner: str
    request_id: str
    operation: str
    url: str
    payload: dict
    digest: str
    expires: float
    prepared: Any


class ChangeEngine:
    def __init__(self, settings, adapter, store: ChangeStore):
        self.settings, self.adapter, self.store = settings, adapter, store
        self.plans: dict[str, Plan] = {}
        self._preview_slots = asyncio.Semaphore(2)

    def authorize_preflight_reads(self, spec, url):
        if spec.target_kind == "table":
            self.settings.authorize(Target.parse(url))
        elif spec.target_kind in {"docx", "sheets", "file"} and self.settings.resource_urls:
            from .resources import Resource

            target = Resource.parse(url)
            if (target.kind, target.token) not in {
                (item.kind, item.token) for item in map(Resource.parse, self.settings.resource_urls)
            }:
                raise BitableError("Change preflight target is outside FEISHU_READ_RESOURCE_URLS.")

    def actor(self, spec=None) -> str:
        if self.settings.identity == "user":
            from fastmcp.server.dependencies import get_access_token

            access = get_access_token()
            if access is None or not access.subject:
                raise BitableError("Feishu user authorization is required; no app fallback.")
            if spec and not set(spec.scopes).intersection(
                (access.claims or {}).get("feishu_granted_scopes", [])
            ):
                raise BitableError("Missing an actually granted Feishu scope; authorize again.")
            raw = "user:" + access.subject
        else:
            raw = "app:" + self.settings.app_id
        return hashlib.sha256(raw.encode()).hexdigest()

    def status(self, request_id: str):
        result = self.store.get(self.actor(), request_id)
        if result is None:
            raise BitableError("No receipt exists for this actor and request_id.")
        return {
            "request_id": request_id,
            "status": result["state"],
            "receipt": result["receipt"],
            "retry_allowed": False,
            "note": "started may be in flight or interrupted by restart; do not repeat it. "
            "An operator must inspect uncertain outcomes before releasing a resource.",
        }

    async def prepare(self, operation: str, url: str, payload: dict, request_id: str):
        if not self.settings.enable_changes:
            raise BitableError("Changes are disabled by the operator.")
        if not isinstance(payload, dict):
            raise BitableError("payload must be a JSON object.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise BitableError("request_id must be 8-100 letters, digits, underscores or hyphens.")
        spec = authorize(self.settings.change_policy, operation, url)
        self.authorize_preflight_reads(spec, url)
        owner = self.actor(spec)
        # Own the input copy; later caller-side mutation cannot change an approved plan.
        digest = fingerprint({"operation": operation, "url": url, "payload": payload})
        payload = json.loads(json.dumps(payload, allow_nan=False))
        existing = self.store.get(owner, request_id)
        if existing:
            if existing["fingerprint"] != digest:
                raise BitableError("request_id is already bound to different content.")
            return self.status(request_id)
        self.plans = {k: v for k, v in self.plans.items() if v.expires > time.monotonic()}
        if len(self.plans) >= 100:
            raise BitableError("Too many outstanding previews; wait for expiry.")
        async with self._preview_slots:
            prepared = await self.adapter.prepare(operation, url, payload, request_id)
        if len(self.plans) >= 100:
            raise BitableError("Too many outstanding previews; wait for expiry.")
        memory = prepared.get("memory_bytes", 0)
        if (
            memory + sum(x.prepared.get("memory_bytes", 0) for x in self.plans.values())
            > 32 * 1024 * 1024
        ):
            raise BitableError("Outstanding previews exceed the memory budget; wait for expiry.")
        plan_id = secrets.token_urlsafe(24)
        self.plans[plan_id] = Plan(
            owner,
            request_id,
            operation,
            url,
            payload,
            digest,
            time.monotonic() + 600,
            prepared,
        )
        return {
            "plan_id": plan_id,
            "confirmation_digest": digest,
            "request_id": request_id,
            "operation": operation,
            "target_url": url,
            "exact_content": json.loads(json.dumps(payload, allow_nan=False)),
            "expires_in_seconds": 600,
            "preconditions": prepared.get("preconditions", {}),
            "confirmation_required": "Ask the user to approve this exact target and content.",
        }

    async def commit(self, plan_id: str, confirmation_digest: str, confirm: bool):
        plan = self.plans.get(plan_id)
        if plan is None or plan.owner != self.actor():
            raise BitableError("Preview is absent or belongs to another user; prepare again.")
        spec = authorize(self.settings.change_policy, plan.operation, plan.url)
        self.authorize_preflight_reads(spec, plan.url)
        self.actor(spec)
        if confirm is not True or not hmac.compare_digest(plan.digest, confirmation_digest):
            raise BitableError("Confirm the exact preview and its confirmation_digest first.")
        existing = self.store.get(plan.owner, plan.request_id)
        if existing:
            return self.status(plan.request_id)
        if plan.expires <= time.monotonic():
            raise BitableError("Preview expired; prepare and confirm again.")
        key = target_key(plan.url, spec.target_kind)
        # Serialize the entire workbook, even when the operator narrowed the URL to a sheet.
        resource = fingerprint(key[:2] if spec.target_kind == "sheets" else key)
        if not self.store.reserve(plan.owner, plan.request_id, plan.digest, resource):
            return self.status(plan.request_id)
        dispatched = False
        try:
            # Re-read after obtaining a cross-process lease. Feishu lacks atomic CAS on some APIs.
            await self.adapter.check(plan.prepared)
            dispatched = True
            receipt = await self.adapter.dispatch(plan.prepared)
        except BaseException as exc:
            state = "unknown" if dispatched else "conflict"
            self.store.finish(
                plan.owner,
                plan.request_id,
                state,
                {
                    "status": state,
                    "operation": plan.operation,
                    "message": "Do not retry an uncertain write; inspect the remote resource first."
                    if dispatched
                    else "Precondition failed; prepare a new confirmed change.",
                },
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, BitableError):
                raise
            raise BitableError("Change failed; inspect its receipt before any retry.") from None
        self.store.finish(plan.owner, plan.request_id, "succeeded", receipt)
        return self.status(plan.request_id)
