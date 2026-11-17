"""No live writes: test preview binding, per-user policy and durable uncertain outcomes."""

import asyncio
from contextvars import ContextVar
from dataclasses import replace

import httpx
import pytest

from feishu_bitable_mcp.bitable_changes import BitableChanges
from feishu_bitable_mcp.change_store import ChangeStore
from feishu_bitable_mcp.changes import ChangeEngine
from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings

URL = "https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01"
PAYLOAD = {"records": [{"fields": {"Title": "private-fictional-content"}}]}


@pytest.fixture
async def context(tmp_path):
    state = {"writes": 0, "timeout": False, "extra_field": False}
    policy = Settings(
        "fictional-app",
        "fictional-secret",
        auth_token="x" * 40,
        enable_changes=True,
        change_policy={"bitable.create_records": [URL], "bitable.update_records": [URL]},
        change_ledger=str(tmp_path / "receipts.sqlite3"),
    )

    async def upstream(request):
        path = request.url.path
        if path.endswith("/internal"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "tenant_access_token": "fictional-tenant-token",
                    "expire": 7200,
                },
            )
        if path.endswith("/fields"):
            fields = [{"field_id": "fldDemoTitle", "field_name": "Title", "type": 1}]
            if state["extra_field"]:
                fields.append({"field_name": "Other", "type": 1})
            data = {"items": fields, "has_more": False}
        elif request.method != "GET":
            state["writes"] += 1
            await asyncio.sleep(0.01)
            if state["timeout"]:
                raise httpx.ReadTimeout("fictional-secret", request=request)
            data = {"records": [{"record_id": "recDemoRecord01"}]}
        else:
            data = {"record": {"record_id": "recDemoRecord01", "fields": {"Title": "before"}}}
        return httpx.Response(200, json={"code": 0, "data": data})

    api = FeishuClient(policy, transport=httpx.MockTransport(upstream))
    adapter = BitableChanges(api)
    store = ChangeStore(policy.change_ledger)
    yield ChangeEngine(policy, adapter, store), state, store
    await api.close()


async def test_preview_confirmation_and_concurrent_deduplication(context):
    engine, state, _ = context
    preview = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    assert state["writes"] == 0 and preview["exact_content"] == PAYLOAD
    with pytest.raises(BitableError, match="Confirm"):
        await engine.commit(preview["plan_id"], preview["confirmation_digest"], False)
    with pytest.raises(BitableError, match="Confirm"):
        await engine.commit(preview["plan_id"], "wrong-digest", True)
    results = await asyncio.gather(
        *(engine.commit(preview["plan_id"], preview["confirmation_digest"], True) for _ in range(2))
    )
    assert state["writes"] == 1
    assert any(x["status"] == "succeeded" for x in results)
    assert engine.status("request-0001")["receipt"]["record_ids"] == ["recDemoRecord01"]
    again = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    assert again["status"] == "succeeded" and state["writes"] == 1


async def test_payload_binding_and_receipt_survive_restart(context):
    engine, state, store = context
    preview = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    restarted = ChangeEngine(engine.settings, engine.adapter, store)
    result = await restarted.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    assert result["status"] == "succeeded" and state["writes"] == 1
    with pytest.raises(BitableError, match="different content"):
        await restarted.prepare("bitable.create_records", URL, {"records": []}, "request-0001")
    assert b"private-fictional-content" not in store.path.read_bytes()
    assert b"fictional-secret" not in store.path.read_bytes()
    assert b"fictional-tenant-token" not in store.path.read_bytes()


async def test_timeout_is_unknown_and_holds_resource_against_new_request_ids(context):
    engine, state, _ = context
    preview = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    state["timeout"] = True
    with pytest.raises(BitableError, match="outcome is unknown"):
        await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    assert engine.status("request-0001")["status"] == "unknown"
    await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    next_preview = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0002")
    with pytest.raises(BitableError, match="uncertain outcome"):
        await engine.commit(next_preview["plan_id"], next_preview["confirmation_digest"], True)
    assert state["writes"] == 1


async def test_schema_conflict_stops_before_dispatch(context):
    engine, state, _ = context
    preview = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    state["extra_field"] = True
    with pytest.raises(BitableError, match="changed after preview"):
        await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    assert state["writes"] == 0
    assert engine.status("request-0001")["status"] == "conflict"


async def test_scope_claims_and_actor_isolation(context, monkeypatch):
    from fastmcp.server import dependencies
    from fastmcp.server.auth import AccessToken

    engine, _, store = context
    policy = replace(
        engine.settings, identity="user", auth_token="", public_url="https://mcp.example.com/mcp"
    )
    engine = ChangeEngine(policy, engine.adapter, store)
    access = [
        AccessToken(
            token="fictional-user",
            client_id="synthetic",
            subject="owner-one",
            scopes=["bitable:app"],
            claims={},
        )
    ]
    monkeypatch.setattr(dependencies, "get_access_token", lambda: access[0])
    with pytest.raises(BitableError, match="actually granted"):
        await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    access[0].claims["feishu_granted_scopes"] = ["base:record:create"]
    preview = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    access[0] = access[0].model_copy(update={"subject": "owner-two"})
    with pytest.raises(BitableError, match="another user"):
        await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)


async def test_target_allowlist_and_expiry(context):
    engine, state, _ = context
    with pytest.raises(BitableError, match="not operator-authorized"):
        await engine.prepare(
            "bitable.create_records",
            URL.replace("tblDemoTable01", "tblOtherTable01"),
            PAYLOAD,
            "request-0001",
        )
    preview = await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-0001")
    engine.plans[preview["plan_id"]].expires = 0
    with pytest.raises(BitableError, match="expired"):
        await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    assert state["writes"] == 0


async def test_write_policy_does_not_bypass_read_policy(context):
    engine, state, store = context
    policy = replace(
        engine.settings, read_tables=frozenset({("OtherDemoBase0001", "tblOtherTable01")})
    )
    engine = ChangeEngine(policy, engine.adapter, store)
    with pytest.raises(BitableError, match="FEISHU_READ_TABLE_URLS"):
        await engine.prepare("bitable.create_records", URL, PAYLOAD, "request-read-denied01")
    assert state["writes"] == 0


async def test_pending_lease_survives_restart_and_only_offline_reconciliation_releases(context):
    engine, _, store = context
    owner = engine.actor()
    assert store.reserve(owner, "request-crash01", "digest", "resource")
    restarted = ChangeStore(str(store.path))
    assert restarted.pending()[0]["state"] == "started"
    with pytest.raises(BitableError, match="holds this resource"):
        restarted.reserve(owner, "request-crash02", "digest2", "resource")
    restarted.reconcile(owner, "request-crash01", "verified_not_applied", "a" * 64)
    assert restarted.pending() == []
    assert restarted.reserve(owner, "request-crash02", "digest2", "resource")
    # Original ID stays permanently bound; reconciliation never deletes it for a retry.
    assert not restarted.reserve(owner, "request-crash01", "digest", "resource")


async def test_separate_store_instances_reserve_only_once(context):
    engine, _, store = context
    other = ChangeStore(str(store.path))
    result = await asyncio.gather(
        asyncio.to_thread(store.reserve, engine.actor(), "request-shared01", "digest", "resource"),
        asyncio.to_thread(other.reserve, engine.actor(), "request-shared01", "digest", "resource"),
    )
    assert sorted(result) == [False, True]


async def test_real_user_contexts_never_use_application_credentials_for_writes(
    tmp_path, monkeypatch
):
    from fastmcp.server import dependencies
    from fastmcp.server.auth import AccessToken

    other_url = URL.replace("tblDemoTable01", "tblDemoTable02")
    settings = Settings(
        "fictional-app",
        "fictional-secret",
        identity="user",
        public_url="https://mcp.example.com/mcp",
        enable_changes=True,
        change_policy={"bitable.create_records": [URL, other_url]},
    )
    current = ContextVar("synthetic_write_user", default=None)
    monkeypatch.setattr(dependencies, "get_access_token", current.get)
    writes = []

    async def upstream(request):
        assert not request.url.path.endswith("/internal")
        if request.method == "GET":
            data = {"items": [{"field_name": "Title", "type": 1}], "has_more": False}
        else:
            writes.append((request.headers["authorization"], request.url.path))
            await asyncio.sleep(0.01)
            data = {"records": [{"record_id": "recDemoRecord01"}]}
        return httpx.Response(200, json={"code": 0, "data": data})

    api = FeishuClient(settings, transport=httpx.MockTransport(upstream))
    engine = ChangeEngine(settings, BitableChanges(api), ChangeStore(str(tmp_path / "receipts.db")))

    async def run(subject, url):
        marker = current.set(
            AccessToken(
                token="fictional-" + subject,
                client_id="test",
                subject=subject,
                scopes=[],
                claims={"feishu_granted_scopes": ["base:record:create"]},
            )
        )
        try:
            plan = await engine.prepare("bitable.create_records", url, PAYLOAD, "same-request-01")
            return await engine.commit(plan["plan_id"], plan["confirmation_digest"], True)
        finally:
            current.reset(marker)

    try:
        results = await asyncio.gather(run("alice", URL), run("bob", other_url))
        assert all(x["status"] == "succeeded" for x in results)
        assert len(writes) == 2
        assert (
            "Bearer fictional-alice",
            "/open-apis/bitable/v1/apps/DemoBaseToken0001/tables/tblDemoTable01/records/batch_create",
        ) in writes
        assert (
            "Bearer fictional-bob",
            "/open-apis/bitable/v1/apps/DemoBaseToken0001/tables/tblDemoTable02/records/batch_create",
        ) in writes
    finally:
        await api.close()
