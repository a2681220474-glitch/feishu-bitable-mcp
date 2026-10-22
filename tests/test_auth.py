"""Authentication tests use fabricated credentials and an in-process HTTP app."""

import hashlib

import httpx
import pytest
from fastmcp import FastMCP

from feishu_bitable_mcp.auth import SingleOwnerTokenVerifier, build_auth

FAKE_TOKEN = "mock-owner-token-with-at-least-32-characters"


def test_empty_token_allows_local_unauthenticated_mode():
    assert build_auth("") is None


@pytest.mark.parametrize("token", ["short", " " * 40, "x" * 32 + "\n"])
def test_rejects_invalid_configured_secret_without_echoing_it(token):
    with pytest.raises(ValueError) as error:
        SingleOwnerTokenVerifier(token)
    assert token not in str(error.value)


@pytest.mark.asyncio
async def test_authentication_uses_digest_and_redacts_result():
    verifier = SingleOwnerTokenVerifier(FAKE_TOKEN)
    assert verifier._token_digest == hashlib.sha256(FAKE_TOKEN.encode()).digest()
    assert FAKE_TOKEN not in repr(verifier)
    assert FAKE_TOKEN not in repr(vars(verifier))
    assert await verifier.verify_token("wrong-token") is None
    assert await verifier.verify_token("") is None
    result = await verifier.verify_token(FAKE_TOKEN)
    assert result is not None
    assert result.scopes == ["read", "create"]
    assert result.client_id == "single-owner"
    assert FAKE_TOKEN not in repr(result)
    assert result.token == "<redacted>"


@pytest.mark.asyncio
async def test_http_rejects_missing_and_invalid_auth_but_allows_owner():
    server = FastMCP("Authentication test", auth=build_auth(FAKE_TOKEN))

    @server.tool
    def example_read() -> dict:
        """Return synthetic data without external requests."""
        return {"synthetic": True}

    app = server.http_app(path="/mcp", stateless_http=True, json_response=True)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            headers = {"Accept": "application/json, text/event-stream"}
            denied = await client.post("/mcp", json=payload, headers=headers)
            assert denied.status_code == 401
            invalid = await client.post(
                "/mcp", json=payload, headers={**headers, "Authorization": "Bearer wrong-token"}
            )
            assert invalid.status_code == 401
            accepted = await client.post(
                "/mcp", json=payload, headers={**headers, "Authorization": f"Bearer {FAKE_TOKEN}"}
            )
            assert accepted.status_code == 200
            assert [tool["name"] for tool in accepted.json()["result"]["tools"]] == ["example_read"]
            assert FAKE_TOKEN not in accepted.text
