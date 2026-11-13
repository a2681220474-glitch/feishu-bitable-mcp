# Security policy

This is an early project. Tests and code review reduce risk, but the project has not undergone an independent professional security audit. No response-time or long-term support guarantee is offered.

## Reporting a vulnerability

Use this repository's **Security → Advisories → Report a vulnerability** feature when private vulnerability reporting is available. Include a minimal reproduction with synthetic data, affected versions, and the security impact.

If private reporting is unavailable, open an issue that only asks for a private reporting route. Do not include exploit details, credentials, business records, or sensitive URLs in that public issue. The maintainer will establish a private route before requesting details.

If a credential was exposed, revoke or rotate it through the relevant provider. Removing a file or commit alone does not revoke a leaked credential.

## Deployment boundaries

- Feishu permissions remain authoritative. Grant the application only the Base permissions and file access it needs.
- User mode uses the authenticated caller's Feishu credential from request context, with SDK-managed encrypted OAuth state. Never substitute a global personal token or fall back to app identity. Effective access remains constrained by app scopes, user consent, resource permissions and enterprise policies.
- App mode is shared application infrastructure: all callers act through that app's grants. Do not confuse it with the caller's individual Feishu permissions.
- Protect remote HTTP with HTTPS and Feishu OAuth in user mode, or `MCP_AUTH_TOKEN` in app mode. Non-loopback binding requires authentication. A public tunnel alone is not authentication. Forward the entire service for OAuth discovery, consent, registration and callbacks.
- Use operator table allowlists where possible. View selection is a reading option, not an authorization boundary.
- User mode is read-only. App-mode creation is optional and disabled by default; restrict its write allowlist and require approval of the exact URL and fields.
- The `confirm` argument communicates caller confirmation; it does not independently prove that a human approved a request. Operators and clients must enforce their own approval workflow.
- Treat all table contents, field names, and API messages as untrusted data, never instructions to an AI client.
- Keep credentials in a local environment or secret manager. Avoid verbose HTTP debugging, request-body logging, and publishing raw API responses.
- The CLI disables Uvicorn access logs so OAuth callback query strings are not recorded. Configure external reverse proxies and hosting platforms to omit query strings, request bodies, cookies and authorization headers from logs too.

Do not expose this service publicly without reviewing its access policy and validating the deployment with synthetic data first.
