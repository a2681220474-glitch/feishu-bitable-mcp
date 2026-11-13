"""GitHub login boundaries use synthetic identities and in-memory OAuth storage."""

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.github import GitHubProvider
from key_value.aio.stores.memory import MemoryStore

from feishu_bitable_mcp.auth import configured_auth
from feishu_bitable_mcp.config import BitableError, Settings

OPTIONS = {
    "github_client_id": "fictional-oauth-app",
    "github_client_secret": "fictional-github-client-secret",
    "github_allowed_ids": frozenset({"123456"}),
    "public_url": "https://mcp.example.com/mcp",
}


@pytest.mark.parametrize("change", [
    {"github_allowed_ids": frozenset()}, {"github_allowed_ids": frozenset({"username"})},
    {"github_client_secret": ""}, {"public_url": ""},
    {"auth_token": "x" * 40}, {"oauth_issuer": "https://identity.example.com/"},
])
def test_github_login_fails_closed_for_missing_or_mixed_configuration(change):
    with pytest.raises(BitableError):
        Settings("fictional-app", "fictional-secret", **(OPTIONS | change))


async def test_github_allowlist_and_discovery(monkeypatch):
    provider = configured_auth(
        Settings("fictional-app", "fictional-secret", **OPTIONS), oauth_storage=MemoryStore()
    )
    identity = ["123456"]

    async def load(_provider, _token):
        return AccessToken(
            token="fictional-upstream-token", client_id="fictional-client",
            subject=identity[0], scopes=["read:user"],
        )

    monkeypatch.setattr(GitHubProvider, "load_access_token", load)
    accepted = await provider.verify_token("fictional-mcp-token")
    assert accepted is not None and accepted.token == "<redacted>"
    assert "fictional-upstream-token" not in repr(accepted)
    identity[0] = "654321"
    assert await provider.verify_token("fictional-mcp-token") is None

    app = FastMCP("Synthetic GitHub login", auth=provider).http_app(path="/mcp")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://mcp.example.com"
        ) as client:
            resource = await client.get("/.well-known/oauth-protected-resource/mcp")
            assert resource.status_code == 200
            metadata = await client.get("/.well-known/oauth-authorization-server")
            assert metadata.status_code == 200
            assert "S256" in metadata.json()["code_challenge_methods_supported"]
