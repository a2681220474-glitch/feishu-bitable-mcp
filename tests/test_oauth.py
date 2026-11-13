"""Real signed JWT verification and discovery with synthetic keys, no live IdP."""

import time

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from joserfc.jwk import RSAKey

from feishu_bitable_mcp import auth
from feishu_bitable_mcp.config import BitableError, Settings

OPTIONS = {
    "oauth_issuer": "https://identity.example.com/",
    "oauth_jwks_url": "https://identity.example.com/.well-known/jwks.json",
    "public_url": "https://mcp.example.com/mcp",
}


@pytest.mark.parametrize("changed", [
    {"oauth_jwks_url": ""}, {"auth_token": "x" * 40},
    {"public_url": "http://mcp.example.com/mcp"},
    {"public_url": "https://mcp.example.com/other"},
    {"oauth_issuer": "https://user:secret@identity.example.com/"},
])
def test_oauth_rejects_incomplete_ambiguous_or_unsafe_settings(changed):
    with pytest.raises(BitableError):
        Settings("fictional-app", "fictional-secret", **(OPTIONS | changed))


async def test_discovery_challenge_and_jwt_claim_boundaries(monkeypatch):
    keys = RSAKeyPair.generate()

    async def fetch_jwks(verifier):
        assert verifier.jwks_uri == OPTIONS["oauth_jwks_url"]
        return {"keys": [RSAKey.import_key(keys.public_key).as_dict()]}

    monkeypatch.setattr(JWTVerifier, "_fetch_jwks", fetch_jwks)
    provider = auth.configured_auth(Settings("fictional-app", "fictional-secret", **OPTIONS))
    server = FastMCP("Synthetic OAuth test", auth=provider)

    @server.tool
    def example_read() -> dict:
        """Return fictional content only."""
        return {"synthetic": True}

    app = server.http_app(path="/mcp", stateless_http=True, json_response=True)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://mcp.example.com"
        ) as client:
            headers = {"Accept": "application/json, text/event-stream"}
            payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            denied = await client.post("/mcp", headers=headers, json=payload)
            assert denied.status_code == 401
            assert "resource_metadata=" in denied.headers["www-authenticate"]
            metadata = await client.get("/.well-known/oauth-protected-resource/mcp")
            assert metadata.status_code == 200
            assert metadata.json()["resource"] == OPTIONS["public_url"]
            assert metadata.json()["authorization_servers"] == [OPTIONS["oauth_issuer"]]
            assert metadata.json()["scopes_supported"] == ["read"]
            claims = {
                "iss": OPTIONS["oauth_issuer"], "aud": OPTIONS["public_url"],
                "scope": "read", "sub": "synthetic-owner", "exp": int(time.time()) + 300,
            }
            for changes, status in [
                ({}, 200), ({"aud": "https://other.example.com"}, 401),
                ({"iss": "https://other.example.com/"}, 401),
                ({"scope": "unrelated"}, 401), ({"exp": 1}, 401),
                ({"exp": None}, 401), ({"nbf": int(time.time()) + 600}, 401),
                ({"sub": ""}, 401),
            ]:
                token = keys.create_token(additional_claims=claims | changes)
                response = await client.post(
                    "/mcp", json=payload, headers=headers | {"Authorization": f"Bearer {token}"}
                )
                assert response.status_code == status
                assert token not in response.text
            token = RSAKeyPair.generate().create_token(additional_claims=claims)
            assert await provider.verify_token(token) is None
            valid = keys.create_token(additional_claims=claims)
            context = await provider.verify_token(valid)
            assert context is not None and context.token == "<redacted>"
            assert valid not in repr(context)
