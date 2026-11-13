# Changelog

## Unreleased

- Add an alternative GitHub OAuth login using the SDK proxy, requiring an explicit
  immutable GitHub user-ID allowlist. Request only read:user, retain consent, and
  restrict client callbacks to ChatGPT. Real browser acceptance remains pending.

- Add explicit `--env-file` and staged, read-only `--doctor` diagnostics. Network checks
  require an explicit authorized test URL; reports omit credentials and record content.
- Add optional external OAuth resource discovery and RS256 JWT verification, including
  issuer, audience, read scope, expiry, subject and not-before checks. OAuth mode is read-only;
  the identity provider must restrict eligible users. Live ChatGPT browser acceptance is pending.
- Retry transient read transport failures with bounded backoff and jitter, limit in-flight
  requests to four, and bound each attempt to 20 seconds. Long Retry-After values stop
  retries instead of causing premature requests. POST requests still are never retried.
- Upgrade FastMCP to 4.1.6 and synchronize the dependency hash lock.
- Document first-use troubleshooting and add macOS/Windows onboarding CI.

Local validation (Python 3.12): 243 synthetic tests passed for both resolved and
hash-locked/wheel installations; Ruff, dependency consistency, package builds,
installed-wheel diagnostics from another directory and stdio discovery passed.
The updated lock has no known vulnerabilities in the advisory scan. Cross-platform
CI and real ChatGPT/identity-provider acceptance must be checked separately.

## 0.1.1 — 2026-11-06

- Redact credentials used by each in-flight request, including both attempts of a refreshed read, even when concurrent calls replace the cached tenant token. Credentials are retained only for that request, not in an accumulating token history.
- Identify the offending field and expected value format in record-creation validation errors. Submitted values remain omitted; field names are bounded and control characters escaped.
- Upgrade FastMCP to 4.1.5 and python-dotenv to 1.2.4, regenerating the hash lock with compatible existing dependency pins. FastMCP no longer pulls in the unused Keyring extras; this server's authentication remains unchanged.
- Upgrade GitHub's checkout/setup-python Actions to v7 for hosted runners. Test hash-locked installation on Python 3.11–3.13 and independently resolved installation on Python 3.12, with `pip check` in each lane.
- Run CI and public-advisory dependency auditing weekly as well as on pushes and pull requests.

Validation: 216 mock-based tests, lint and `pip check` passed locally with both hash-locked and independently resolved dependencies. Wheel installation and stdio tool discovery passed. The lock's 70 applicable dependencies have no known vulnerabilities in the public-advisory scan. The added regression tests use fictional data and MockTransport. No real Feishu records are read or written during this maintenance. The limitations documented for v0.1.0 still apply: public-release live view/write semantics and ChatGPT web OAuth integration are not verified.

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
