"""Caller authentication for an operator-controlled, single-owner deployment.

Static Bearer verification or external OAuth resource-server integration.
The external identity provider handles browser login and authorization.
Feishu credentials authenticate the upstream application, not the MCP caller.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import time

from fastmcp.server.auth import AccessToken, AuthProvider, RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl

from .config import Settings


class SingleOwnerTokenVerifier(TokenVerifier):
    """Verify one high-entropy Bearer secret, retaining only its SHA-256 digest.

    The owner can read and request record creation; table and write enablement
    policy must still be enforced by the application for every write.
    """

    def __init__(self, token: str) -> None:
        if not isinstance(token, str) or len(token) < 32 or any(c.isspace() for c in token):
            raise ValueError(
                "MCP_AUTH_TOKEN must contain at least 32 characters without whitespace."
            )
        super().__init__(required_scopes=["read"])
        self._token_digest = hashlib.sha256(token.encode("utf-8")).digest()

    def __repr__(self) -> str:
        return "SingleOwnerTokenVerifier()"

    async def verify_token(self, token: str) -> AccessToken | None:
        if not isinstance(token, str):
            return None
        supplied_digest = hashlib.sha256(token.encode("utf-8")).digest()
        if not hmac.compare_digest(self._token_digest, supplied_digest):
            return None
        # This is an authentication result, not a credential for downstream use.
        # Omitting the real token also keeps its repr and tool context redacted.
        return AccessToken(token="<redacted>", client_id="single-owner", scopes=["read", "create"])


def build_auth(token: str) -> AuthProvider | None:
    """Build optional caller auth; the CLI separately enforces safe host binding."""
    return SingleOwnerTokenVerifier(token) if token else None


class OAuthTokenVerifier(TokenVerifier):
    """Require exp/sub, honor nbf, and remove raw credentials from auth context."""

    def __init__(self, verifier: JWTVerifier):
        super().__init__(required_scopes=["read"])
        self.verifier = verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        result = await self.verifier.verify_token(token)
        if result is None or result.expires_at is None or not result.subject:
            return None
        not_before = result.claims.get("nbf")
        if not_before is not None and (
            type(not_before) not in (int, float)
            or not math.isfinite(not_before)
            or not_before > time.time()
        ):
            return None
        return AccessToken(
            token="<redacted>", client_id="oauth-user", subject=result.subject,
            scopes=result.scopes, expires_at=result.expires_at,
        )


class AllowedGitHubProvider(GitHubProvider):
    """Use SDK OAuth proxy and allow only explicitly configured immutable user IDs."""

    def __init__(self, allowed_ids: frozenset[str], **kwargs):
        self.allowed_ids = allowed_ids
        super().__init__(**kwargs)

    async def load_access_token(self, token: str) -> AccessToken | None:
        result = await super().load_access_token(token)
        if result is None or result.subject not in self.allowed_ids:
            return None
        return AccessToken(
            token="<redacted>", client_id="github-user", subject=result.subject,
            scopes=result.scopes, expires_at=result.expires_at,
        )


def configured_auth(settings: Settings, *, oauth_storage=None) -> AuthProvider | None:
    """Select SDK-managed GitHub login, an external issuer, or static Bearer auth."""
    if settings.github_client_id:
        return AllowedGitHubProvider(
            allowed_ids=settings.github_allowed_ids,
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            base_url=settings.public_url.removesuffix("/mcp"),
            required_scopes=["read:user"],
            client_storage=oauth_storage,
            require_authorization_consent=True,
            allowed_client_redirect_uris=["https://chatgpt.com/*"],
        )
    if not settings.oauth_issuer:
        return build_auth(settings.auth_token)
    verifier = JWTVerifier(
        jwks_uri=settings.oauth_jwks_url,
        issuer=settings.oauth_issuer,
        audience=settings.public_url,
        algorithm="RS256",
        required_scopes=["read"],
    )
    return RemoteAuthProvider(
        token_verifier=OAuthTokenVerifier(verifier),
        authorization_servers=[AnyHttpUrl(settings.oauth_issuer)],
        base_url=settings.public_url.removesuffix("/mcp"),
        resource_name="Feishu Bitable MCP",
    )
