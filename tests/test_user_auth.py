"""Feishu user credentials stay server-side and never fall back to app identity."""

import asyncio
import base64
import hashlib
import json
import re
from contextvars import ContextVar
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastmcp.server.auth import AccessToken
from key_value.aio.stores.memory import MemoryStore

from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings
from feishu_bitable_mcp.user_auth import (
    TOKEN_URL,
    FeishuProvider,
    FeishuTokenClient,
    FeishuUserVerifier,
)


async def test_complete_synthetic_oauth_consent_code_pkce_and_mcp_read(monkeypatch):
    from feishu_bitable_mcp import server

    policy = settings()
    upstream_calls = []
    blocked = [False]

    def upstream(request):
        upstream_calls.append(request)
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json={
                "code": 0, "access_token": "fictional-person-token", "expires_in": 7200,
                "refresh_token": "fictional-refresh-token", "refresh_token_expires_in": 86400,
                "scope": " ".join(policy.user_scopes),
            })
        if request.url.path.endswith("/user_info"):
            if blocked[0]:
                return httpx.Response(401, json={"code": 99991668, "msg": "Revoked"})
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "fictional-user"}})
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer fictional-person-token"
        return httpx.Response(200, json={"code": 0, "data": {
            "items": [{"block_id": "fictional-block", "text": {"elements": []}}],
            "has_more": False,
        }})

    transport = httpx.MockTransport(upstream)
    provider = FeishuProvider(policy, client_storage=MemoryStore())
    provider._token_validator = FeishuUserVerifier(list(policy.user_scopes), transport=transport)
    monkeypatch.setattr(provider, "_create_upstream_oauth_client", lambda: FeishuTokenClient(
        policy, transport=transport
    ))
    monkeypatch.setattr(server, "configured_auth", lambda _: provider)
    api = FeishuClient(policy, transport=transport)
    app = server.build_server(policy, api).http_app(
        path="/mcp", stateless_http=True, json_response=True
    )
    callback = "https://chatgpt.com/connector/oauth/synthetic"
    verifier = "synthetic-pkce-verifier-" + "x" * 43
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://mcp.example.com"
        ) as browser:
            registration = await browser.post("/register", json={
                "client_name": "Synthetic ChatGPT", "redirect_uris": [callback],
                "token_endpoint_auth_method": "none", "response_types": ["code"],
                "grant_types": ["authorization_code", "refresh_token"],
            })
            assert registration.status_code == 201, registration.text
            client_id = registration.json()["client_id"]
            start = await browser.get("/authorize", params={
                "client_id": client_id, "redirect_uri": callback, "response_type": "code",
                "code_challenge": challenge, "code_challenge_method": "S256",
                "state": "synthetic-client-state", "scope": " ".join(policy.user_scopes),
                "resource": policy.public_url,
            })
            assert start.status_code in {302, 307}, start.text
            consent = await browser.get(start.headers["location"])
            assert consent.status_code == 200
            fields = dict(re.findall(r'name="(txn_id|csrf_token)" value="([^"]+)"', consent.text))
            assert set(fields) == {"txn_id", "csrf_token"}
            approve = await browser.post(
                str(consent.url), data=fields | {"action": "approve"},
                headers={"Origin": "https://mcp.example.com"},
            )
            assert approve.status_code in {302, 303, 307}, approve.text
            authorization = urlsplit(approve.headers["location"])
            assert authorization.hostname == "accounts.feishu.cn"
            state = parse_qs(authorization.query)["state"][0]
            done = await browser.get(
                "/auth/callback", params={"code": "fictional-code", "state": state}
            )
            assert done.status_code in {302, 303, 307}, done.text
            client_code = parse_qs(urlsplit(done.headers["location"]).query)["code"][0]
            token_response = await browser.post("/token", data={
                "grant_type": "authorization_code", "client_id": client_id,
                "code": client_code, "redirect_uri": callback, "code_verifier": verifier,
                "resource": policy.public_url,
            })
            assert token_response.status_code == 200, token_response.text
            assert "fictional-person-token" not in token_response.text
            assert "fictional-refresh-token" not in token_response.text
            access = token_response.json()["access_token"]
            result = await browser.post("/mcp", headers={
                "Authorization": f"Bearer {access}",
                "Accept": "application/json, text/event-stream",
            }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "read_document", "arguments": {
                    "url": "https://example.feishu.cn/docx/DocxDemoToken0001",
                },
            }})
            assert result.status_code == 200, result.text
            assert result.json()["result"]["isError"] is False
            assert "fictional-person-token" not in result.text
            refreshed = await browser.post("/token", data={
                "grant_type": "refresh_token", "client_id": client_id,
                "refresh_token": token_response.json()["refresh_token"],
            })
            assert refreshed.status_code == 200, refreshed.text
            assert "fictional-refresh-token" not in refreshed.text
            assert any(
                r.url.path.endswith("/oauth/token")
                and json.loads(r.content).get("grant_type") == "refresh_token"
                for r in upstream_calls
            )
            blocked[0] = True
            revoked = await browser.post("/mcp", headers={
                "Authorization": f"Bearer {refreshed.json()['access_token']}",
                "Accept": "application/json, text/event-stream",
            }, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            assert revoked.status_code == 401
    assert not any(r.url.path.endswith("/internal") for r in upstream_calls)


def settings(**kwargs):
    return Settings("fictional-app", "fictional-secret", identity="user",
                    public_url="https://mcp.example.com/mcp", **kwargs)


@pytest.mark.parametrize("kwargs", [{"auth_token": "x" * 40}, {"enable_writes": True}])
def test_user_mode_does_not_mix_identity_or_writes(kwargs):
    with pytest.raises(BitableError):
        settings(**kwargs)


async def test_token_exchange_and_refresh_are_json_and_never_retry():
    requests = []

    def reply(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body["client_id"] == "fictional-app"
        assert body["client_secret"] == "fictional-secret"
        assert request.headers["content-type"].startswith("application/json")
        return httpx.Response(200, json={
            "code": 0, "access_token": "fictional-user-token", "expires_in": 7200,
            "refresh_token": "fictional-refresh", "refresh_token_expires_in": 86400,
        })

    client = FeishuTokenClient(settings(), transport=httpx.MockTransport(reply))
    try:
        token = await client.fetch_token(TOKEN_URL, code="fictional-code", code_verifier="verifier")
        assert token["refresh_expires_in"] == 86400
        await client.refresh_token(TOKEN_URL, refresh_token="fictional-refresh")
        assert len(requests) == 2
        assert json.loads(requests[1].content)["grant_type"] == "refresh_token"
    finally:
        await client.aclose()


async def test_authorization_error_preserves_code_without_echoing_secrets():
    from fastmcp.server.auth.oauth_proxy.upstream import OAuthError

    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(400, json={
            "code": 20001, "msg": "fictional-secret fictional-refresh-token",
        })

    client = FeishuTokenClient(settings(), transport=httpx.MockTransport(reply))
    try:
        with pytest.raises(OAuthError) as error:
            await client.fetch_token(TOKEN_URL, code="fictional-code")
        assert "20001" in str(error.value)
        assert "fictional-secret" not in str(error.value)
        assert "fictional-refresh-token" not in str(error.value)
        assert len(requests) == 1
    finally:
        await client.aclose()


async def test_feishu_verifier_checks_real_user_info_shape_without_returning_profile():
    verifier = FeishuUserVerifier([], transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={"code": 0, "data": {"open_id": "fictional-user", "email": "private-profile"}}
    )))
    result = await verifier.verify_token("fictional-user-token")
    assert result is not None and result.subject == "fictional-user"
    assert result.claims == {"sub": "fictional-user"}


async def test_concurrent_users_never_share_an_upstream_credential(monkeypatch):
    from fastmcp.server import dependencies

    current = ContextVar("synthetic_user_token", default=None)
    monkeypatch.setattr(dependencies, "get_access_token", current.get)
    received = []

    async def reply(request):
        assert not request.url.path.endswith("/internal")
        await asyncio.sleep(.01)
        received.append(request.headers["authorization"])
        return httpx.Response(200, json={"code": 0, "data": {}})

    api = FeishuClient(settings(), transport=httpx.MockTransport(reply))

    async def call(token):
        marker = current.set(AccessToken(token=token, client_id="fictional", scopes=[]))
        try:
            await api.request("GET", "/docx/v1/documents/DemoDocument0001")
        finally:
            current.reset(marker)

    try:
        await asyncio.gather(call("fictional-user-one"), call("fictional-user-two"))
        assert set(received) == {"Bearer fictional-user-one", "Bearer fictional-user-two"}
        with pytest.raises(BitableError, match="Sign in"):
            await api.token()
    finally:
        await api.close()


def test_proxy_uses_sdk_consent_storage_and_feishu_endpoints():
    provider = FeishuProvider(settings(), client_storage=MemoryStore())
    assert provider._upstream_token_endpoint == TOKEN_URL
    assert "feishu.cn" in provider._upstream_authorization_endpoint


async def test_sdk_default_state_is_encrypted_and_survives_reconstruction(monkeypatch, tmp_path):
    from fastmcp.server.auth.oauth_proxy import proxy

    monkeypatch.setattr(proxy.settings, "home", tmp_path)
    first = FeishuProvider(settings())
    secrets = {
        "access_token": "fictional-persisted-user",
        "refresh_token": "fictional-persisted-refresh",
    }
    await first._client_storage.put(key="synthetic-state", value=secrets)
    second = FeishuProvider(settings())
    assert await second._client_storage.get(key="synthetic-state") == secrets
    for path in tmp_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert b"fictional-persisted-user" not in content
            assert b"fictional-persisted-refresh" not in content
