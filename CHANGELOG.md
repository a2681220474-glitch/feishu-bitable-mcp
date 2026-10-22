# Changelog

## 0.1.0 — 2026-10-22

Initial public release, independently implemented from an earlier private prototype's generic requirements.

- URL-driven Base and table metadata, full field configuration, paginated raw records, and schema inspection tools.
- Forward an optional view identifier to record reads; preserve upstream fields and pagination metadata.
- Tenant application credentials, cached token refresh, bounded HTTP timeouts, and safe read retries.
- Strict URL validation and operator-configured table access controls.
- Read-only tool registration by default; optional single-record creation requires an explicit write allowlist, field validation, and caller confirmation.
- Streamable HTTP at `/mcp`, optional stdio transport, and bearer authentication for remote HTTP use.
- Mock-based tests, a buildable Python package, and installation/security documentation.

Validation: 203 Mock-based tests, lint, and package builds passed in GitHub CI on
Python 3.11, 3.12, and 3.13. Local Python 3.12 checks also covered a clean wheel
installation, stdio tool discovery, and a real localhost HTTP process serving only
fictional data. Credential/history scanning and dependency auditing passed before
publication. These checks are not a professional security audit.

Live Feishu view filtering, live record creation in this implementation, and
ChatGPT web OAuth integration remain unverified. Historical private prototype
tests are not evidence of external adoption or production use.
