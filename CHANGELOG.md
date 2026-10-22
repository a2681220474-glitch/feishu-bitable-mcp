# Changelog

## 0.1.0 — Unreleased

Initial open-source candidate, independently prepared from an earlier private prototype.

- URL-driven Base and table metadata, full field configuration, paginated raw records, and schema inspection tools.
- Forward an optional view identifier to record reads; preserve upstream fields and pagination metadata.
- Tenant application credentials, cached token refresh, bounded HTTP timeouts, and safe read retries.
- Strict URL validation and operator-configured table access controls.
- Read-only tool registration by default; optional single-record creation requires an explicit write allowlist, field validation, and caller confirmation.
- Streamable HTTP at `/mcp`, optional stdio transport, and bearer authentication for remote HTTP use.
- Mock-based tests, a buildable Python package, and installation/security documentation.

No public release or external adoption is claimed by this entry. A release date and tag will be recorded only after publication.
