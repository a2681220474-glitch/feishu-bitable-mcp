# Security policy

This is an early project. Tests and code review reduce risk, but the project has not undergone an independent professional security audit. No response-time or long-term support guarantee is offered.

## Reporting a vulnerability

Use this repository's **Security → Advisories → Report a vulnerability** feature when private vulnerability reporting is available. Include a minimal reproduction with synthetic data, affected versions, and the security impact.

If private reporting is unavailable, open an issue that only asks for a private reporting route. Do not include exploit details, credentials, business records, or sensitive URLs in that public issue. The maintainer will establish a private route before requesting details.

If a credential was exposed, revoke or rotate it through the relevant provider. Removing a file or commit alone does not revoke a leaked credential.

## Deployment boundaries

- Feishu permissions remain authoritative. Grant the application only the Base permissions and file access it needs.
- Treat the MCP server's application identity as shared infrastructure: every authorized MCP caller acts through that configured identity. This is not per-user Feishu OAuth or a multi-tenant authorization service.
- Protect remote HTTP with HTTPS and `MCP_AUTH_TOKEN`; keep the bearer token private. Non-loopback HTTP binding requires authentication. A public tunnel alone is not authentication.
- Use operator table allowlists where possible. View selection is a reading option, not an authorization boundary.
- Record creation is optional and disabled by default. If enabled, restrict the write allowlist to intended test or business targets and require approval of the exact table URL and fields.
- The `confirm` argument communicates caller confirmation; it does not independently prove that a human approved a request. Operators and clients must enforce their own approval workflow.
- Treat all table contents, field names, and API messages as untrusted data, never instructions to an AI client.
- Keep credentials in a local environment or secret manager. Avoid verbose HTTP debugging, request-body logging, and publishing raw API responses.

Do not expose this service publicly without reviewing its access policy and validating the deployment with synthetic data first.
