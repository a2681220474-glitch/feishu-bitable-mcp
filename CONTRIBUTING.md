# Contributing

Small, focused improvements are welcome. This project focuses on Feishu Bitable and a small MCP tool surface.

## Local development

Use Python 3.11 or newer. CI exercises Python 3.11, 3.12, and 3.13; support for other interpreter versions should be verified before being claimed.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check src tests
pytest
python -m build
```

The automated suite uses mock responses and synthetic identifiers. It requires no Feishu credentials and should not call live Feishu services.

## Changes and tests

Describe the concrete problem, the intended behavior, and how you verified it. Add regression coverage for changes to authorization, URL validation, pagination, retries, token handling, or field validation. Prefer a small fix over adding unrelated platform capabilities.

For API behavior changes, link the official Feishu documentation and distinguish mock verification from live integration testing. A passing mock test does not prove a tenant's permissions or a particular view's filtering behavior.

Use synthetic fixtures. Do not commit `.env`, application credentials, bearer tokens, cookies, authorization headers, real Base/table/view identifiers, business records, logs, or screenshots containing personal or organizational information. Sanitize error messages and reports before opening an issue.

Live integration testing requires a separately authorized test Base. Do not use a production table for test writes. Never add credentials to GitHub Actions secrets merely to run the default test suite.

Changes to record creation must preserve the explicit enable switch, operator write allowlist, field validation, and confirmation requirement. Do not add update, delete, batch writes, or arbitrary API/shell tools as incidental scope.

## Licensing and security

Submit only code and examples you have the right to contribute. Contributions are expected to be available under this project's MIT license; preserve attribution for any permitted third-party material.

Follow [SECURITY.md](SECURITY.md) for suspected vulnerabilities. Do not publish credentials or exploit details in a public issue.
