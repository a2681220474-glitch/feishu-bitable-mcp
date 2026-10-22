# Third-party dependencies and source provenance

This repository independently implements generic MCP and Feishu OpenAPI behavior.
It does not include the private prototype's configuration, business data, private
documentation, deployment history, CLI authentication state, or third-party SDK source.
It is not affiliated with Feishu, Lark, or OpenAI.

The project's MIT license covers only its own source and documentation. Dependencies
retain their respective licenses. Installing dependencies does not relicense them as MIT.
Before publication, the maintainer must confirm they have the right to release this work;
code provenance alone cannot determine employment or other contractual obligations.

## Direct dependencies

| Distribution | Tested version | License | Source |
| --- | --- | --- | --- |
| fastmcp | 4.1.3 | Apache-2.0 | https://github.com/PrefectHQ/fastmcp |
| httpx | 0.28.1 | BSD-3-Clause | https://github.com/encode/httpx |
| python-dotenv | 1.2.2 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |

## Runtime dependency review

The tested Python 3.12 environment resolves 69 runtime distributions, including
the three direct dependencies. `requirements-dev.lock` pins the development and
runtime environment with public PyPI hashes. Platform/Python-specific dependencies
may differ; CI installs the package on Python 3.11–3.13.

License metadata was reviewed for all runtime distributions, following extras
declared by dependencies. The resolved set uses MIT, MIT-0, Apache-2.0, BSD-2-Clause,
BSD-3-Clause, ISC, Unlicense, PSF-2.0, and MPL-2.0 licenses, plus explicit alternatives.
No runtime distribution in this reviewed environment has missing license metadata.

The MPL-2.0 component is `certifi` (Mozilla CA certificate bundle). It is downloaded
as a separate dependency; this repository does not modify or vendor that bundle.
If distributing an application bundle or container containing dependencies, preserve
their notices/licenses and meet the applicable source obligations, including those
of certifi. A permissive project license does not waive those obligations.

The repository does not vendor dependencies. Their installed distribution metadata
and license files are the authoritative notices for the exact versions being used.

## Public API references

- [Feishu Open Platform](https://open.feishu.cn/document/)
- [Feishu official MCP](https://github.com/larksuite/lark-openapi-mcp)
- [Feishu official Python SDK](https://github.com/larksuite/oapi-sdk-python)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP](https://gofastmcp.com/)

These links document protocols and alternatives; they do not imply endorsement.
