"""Feishu user login through the SDK OAuth proxy; tokens stay server-side."""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.oauth_proxy.upstream import OAuthError

from .config import Settings

AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


class FeishuTokenClient:
    """Adapt Feishu's JSON token endpoint to the SDK's narrow upstream contract."""

    def __init__(self, settings: Settings, *, transport=None):
        self.client_id = settings.app_id
        self.client_secret = settings.app_secret
        self._http = httpx.AsyncClient(timeout=20, follow_redirects=False, transport=transport)

    async def aclose(self):
        await self._http.aclose()

    async def fetch_token(self, url: str, *, grant_type="authorization_code", **params):
        if url != TOKEN_URL:
            raise OAuthError(error="invalid_request", description="Unexpected token endpoint.")
        body = {
            "client_id": self.client_id, "client_secret": self.client_secret,
            "grant_type": grant_type,
            **{key: value for key, value in params.items() if value},
        }
        status, code = "network", "unknown"
        try:
            # Authorization codes and rotating refresh tokens must never be retried here.
            response = await self._http.post(TOKEN_URL, json=body)
            status = response.status_code
            payload = response.json()
            if isinstance(payload, dict) and type(payload.get("code")) is int:
                code = payload["code"]
            valid = (
                response.is_success and isinstance(payload, dict)
                and payload.get("code", 0) == 0 and not payload.get("error")
                and isinstance(payload.get("access_token"), str)
                and bool(payload["access_token"])
                and type(payload.get("expires_in")) is int and payload["expires_in"] > 0
            )
        except (httpx.HTTPError, ValueError):
            valid = False
        if not valid:
            raise OAuthError(
                error="invalid_grant",
                description=(
                    f"Feishu authorization failed (HTTP {status}; code={code}). "
                    "Check app settings or sign in again."
                ),
            ) from None
        token = dict(payload)
        token["expires_at"] = int(time.time()) + token["expires_in"]
        if "refresh_token_expires_in" in token:
            token["refresh_expires_in"] = token["refresh_token_expires_in"]
        return token

    async def refresh_token(self, url: str, *, refresh_token=None, **params):
        result = await self.fetch_token(
            url, grant_type="refresh_token", refresh_token=refresh_token, **params
        )
        if "refresh_token" not in result:
            result["refresh_token"] = refresh_token
        return result


class FeishuUserVerifier(TokenVerifier):
    """Validate the upstream user; Feishu APIs enforce resource and data scopes."""

    def __init__(self, scopes: list[str], *, transport=None):
        super().__init__(required_scopes=scopes)
        self.transport = transport

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, transport=self.transport
            ) as client:
                response = await client.get(
                    USER_INFO_URL, headers={"Authorization": f"Bearer {token}"}
                )
            payload = response.json()
            user = payload.get("data", {}) if isinstance(payload, dict) else {}
            subject = user.get("open_id")
            if (
                response.is_success and payload.get("code") == 0
                and isinstance(subject, str) and subject
            ):
                return AccessToken(
                    token=token, client_id=subject, subject=subject,
                    scopes=self.required_scopes, claims={"sub": subject},
                )
        except (httpx.HTTPError, ValueError, AttributeError):
            pass
        return None


class FeishuProvider(OAuthProxy):
    """Keep SDK consent, PKCE, client registration, encrypted state and refresh."""

    def __init__(self, settings: Settings, *, client_storage=None):
        self.feishu_settings = settings
        super().__init__(
            upstream_authorization_endpoint=AUTHORIZE_URL,
            upstream_token_endpoint=TOKEN_URL,
            upstream_client_id=settings.app_id,
            upstream_client_secret=settings.app_secret,
            token_verifier=FeishuUserVerifier(list(settings.user_scopes)),
            valid_scopes=list(settings.user_scopes),
            base_url=settings.public_url.removesuffix("/mcp"),
            client_storage=client_storage,
            forward_pkce=True,
            forward_resource=False,
            require_authorization_consent=True,
            allowed_client_redirect_uris=["https://chatgpt.com/*"],
        )

    def _create_upstream_oauth_client(self) -> Any:
        return FeishuTokenClient(self.feishu_settings)
