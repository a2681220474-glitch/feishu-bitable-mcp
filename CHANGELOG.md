# Changelog

## Post-rc1 development — unreleased

- Add opt-in named changes across Bitable, Docx, online Sheets and Drive XLSX through
  prepare_change / commit_change / get_change_status. Existing read-only defaults stay intact.
- Separate operation/resource allowlists and actual user-granted scopes; do not infer
  write grants from requested configuration or fall back to application credentials.
- Persist single-dispatch receipts and resource leases in private SQLite storage, bind
  previews to actor/content/expiry, check optimistic snapshots, and hold uncertain outcomes.
- Add offline operator reconciliation without making old request IDs retryable.
- Bound batch sizes, cells and basic styles; insert rows explicitly for Sheets append.
  Preserve unrelated OOXML parts during XLSX edits and refuse unsupported workbooks.
- Keep same-token XLSX overwrite experimental and separately gated; the transport follows
  official CLI source, with no claim of verified Drive version-history behavior.

Only synthetic transport/OAuth/workbook tests have run. No live Feishu resource or app
configuration was modified. Strict atomic CAS, complex document blocks and full Base
reconstruction remain unsupported. See docs/changes.md for exact payloads and limitations.

## 0.2.0 development candidate — unreleased

- Add Feishu personal OAuth via the SDK proxy, with consent, PKCE, encrypted state,
  refresh and reauthorization. Per-request user credentials never fall back to app identity.
- Add --setup with hidden secret input and exclusive private config creation; preserve
  --env-file, --doctor, existing application mode and opt-in guarded record creation.
- Add read_document, get_spreadsheet_info, read_spreadsheet, read_excel_file and
  resolve_resource for docx, online Sheets, uploaded .xlsx and Wiki resolution.
- Preserve raw document blocks and record pages, use explicit cell windows and Excel row
  cursors, reject oversized/encrypted/macro workbooks, and never execute formulas.
- Add safe read transport retries, concurrency and attempt deadlines, FastMCP 4.1.6 with
  a synchronized hash lock, and macOS/Windows onboarding CI.
- Update three-language readmes and deployment/authentication guidance.

Validation uses synthetic data, including the complete OAuth flow, refresh, revocation,
concurrent user isolation, new read tools and workbook parsing. Real Feishu/ChatGPT
browser acceptance is pending. No real resource is created or modified during development.

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
