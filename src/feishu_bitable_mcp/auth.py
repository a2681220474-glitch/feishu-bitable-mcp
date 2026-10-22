"""Caller authentication for an operator-controlled, single-owner deployment.

This verifier is not an OAuth authorization server. Interactive clients that
require OAuth discovery need an authenticating OAuth gateway in front of it.
Feishu credentials authenticate the upstream application, not the MCP caller.
"""

from __future__ import annotations

import hashlib
import hmac

from fastmcp.server.auth import AccessToken, AuthProvider, TokenVerifier


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
