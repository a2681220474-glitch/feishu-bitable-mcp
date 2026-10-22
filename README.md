# Feishu Bitable MCP

通过飞书多维表格 URL 读取 Base 信息、字段结构和原始记录的轻量 Python MCP 服务。
默认只读；可选开启有表白名单和字段校验的单条记录创建。

这是社区项目，与飞书、Lark 或 OpenAI 没有官方隶属关系。当前是 `0.1.0` 开源候选版。
原型曾在 ChatGPT 网页端完成读取及固定测试表创建；本版重新实现后以 Mock 自动化测试验证，
没有对真实飞书表执行集成读写，也没有验证当前 ChatGPT 网页端的认证流程。

## 能力与边界

| 工具 | 参数 | 行为 |
| --- | --- | --- |
| `get_bitable_info` | `url` | 返回 URL 坐标、Base 信息和精确匹配的表元数据 |
| `list_fields` | `url` | 读取全部字段页，保留原始属性，增加可读类型名 |
| `list_records` | `url, page_size=100, page_token=None` | 返回一页原始记录和下一页标记；页大小 1–500 |
| `inspect_table` | `url, sample_size=10` | 表信息、完整字段结构、主字段、API 总数和首批原始样本 |
| `create_record` | `url, fields, confirm=false` | 默认不注册；配置允许后创建一条记录 |

- 只接受 `https://*.feishu.cn/base/<app_token>?table=<table_id>`；`view` 可选。
  不支持 Wiki、短链接、BaseApp 或国际版 Lark 域名。
- 服务只从 URL 提取 ID，API 请求目的地固定为 `open.feishu.cn`。
- 读取指定视图时转发 `view_id`。实际筛选、排序和可见字段行为取决于飞书 API，
  这里仅有参数转发测试，不能将视图当成权限隔离边界。`total` 保留上游含义，未保证是视图筛选后的数量。
- 记录的所有 `fields` 和附加记录属性都会保留；不会自动概括内容。
  `inspect_table` 的首批记录不是统计抽样。
- 单次记录调用只返回一页。调用方应在 `has_more=true` 时继续传 `page_token`；不会静默只取最后一页。
- 字段中公式、查找引用、关联目标、选项等配置按飞书返回原样保留。上游未提供的配置不会推断。
- 仅支持企业自建应用的 `tenant_access_token`；没有 CLI、用户 OAuth 或数据库依赖。
  应用只能访问其已授权资源；这些身份不等于最终用户本人的权限。
- 没有更新、删除、批量写入、建表或修改字段工具。

以下 URL、字段和记录均为虚构示例，不能用于真实 API 调用：

```text
https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01&view=vewDemoView1
```

## 安装与本地启动

需要 Python 3.11+。已配置 Python 3.11–3.13 CI；本地实际测试版本见发布记录。

```bash
git clone https://github.com/a2681220474-glitch/feishu-bitable-mcp.git
cd feishu-bitable-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
cp .env.example .env
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。
仓库公开前，可直接在下载/解压后的目录从 `python3 -m venv .venv` 开始。

仅在本地 `.env` 设置：

```dotenv
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

从[飞书开发者后台](https://open.feishu.cn/app)的企业自建应用「凭证与基础信息」获取凭证。
在该应用开通当前 API 所需的多维表格读取权限、发布所需配置，并在目标 Base 设置中授权该应用访问。
读取失败时先检查应用权限与资源授权，不要把 Secret 或访问令牌贴到 issue。

```bash
feishu-bitable-mcp
```

默认监听 `http://127.0.0.1:8000/mcp`（Streamable HTTP）。仅在当前工作目录加载 `.env`；
已有环境变量优先。可用 `--host`、`--port` 或 `MCP_HOST`、`MCP_PORT` 改端口。
服务启动和协议握手不验证飞书凭证，实际工具调用才连接飞书。

```bash
curl -i http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"local-check","version":"1.0"}}}'
```

也支持本机 MCP 客户端使用 stdio：

```bash
feishu-bitable-mcp --transport stdio
```

`examples/stdio-client.json` 是通用配置示例；替换路径，并通过客户端环境设置凭证，避免依赖工作目录。

## 远程 HTTP 与 ChatGPT

飞书 App Secret 保护的是上游调用；MCP 调用方需要另行鉴权。
除回环地址外，启动必须配置至少 32 字符的随机 `MCP_AUTH_TOKEN`。例如在自己的环境中生成：

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

将生成值保存在自己的 `.env`/secret manager，不提交或发送到聊天。支持自定义 HTTP 请求头的客户端使用：

```text
Authorization: Bearer <your MCP_AUTH_TOKEN>
```

该模式面向单维护者自托管：持有这个凭证的调用方共享同一个飞书应用授权范围。
它不是 OAuth 授权服务器，不提供每用户授权、撤销 UI 或独立的人类审批服务。
可用 `FEISHU_READ_TABLE_URLS` 限制所有读取；逗号分隔完整 URL，匹配的是 Base+表，忽略 view。

ChatGPT 网页端需要能从其网络访问的 HTTPS `/mcp` 地址。
对于需要 OAuth 的客户端，应先部署受信任的 OAuth/OIDC 网关，并让网关验证客户端授权、
通过服务器侧配置把请求转发到有 Bearer 保护的本服务。OAuth 网关本身不在本项目范围内。
本版没有完成 ChatGPT 网页端的端到端认证验证；不会声称粘贴一个 URL 就一定可用。
支持手动设置 Bearer 请求头的 MCP 客户端可直接连接。

临时隧道只解决 HTTPS/可达性。需要时可在 macOS 安装 `brew install cloudflared`，
在本地已经配置鉴权后运行 `cloudflared tunnel --url http://127.0.0.1:8000`，
最终 URL 为 `https://<generated-host>.trycloudflare.com/mcp`。
即使服务仍绑定回环地址，隧道也会使其公开可达，所以必须配置鉴权。
不要公开无认证的业务接口；客户端不支持配置凭证时，应使用合适的 OAuth 网关。

## 可选：创建一条记录

默认工具列表不含 `create_record`。操作者必须同时设置：

```dotenv
FEISHU_ENABLE_WRITES=true
MCP_AUTH_TOKEN=<your random secret of at least 32 characters>
FEISHU_WRITE_TABLE_URLS=https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01
```

白名单只写入服务器环境，不允许客户端自行扩大。应用还需拥有目标表的记录创建权限。
如果设置了读取白名单，写入表也必须在读取白名单内，字段校验才能进行。

调用前，先用 `list_fields` 查看真实字段，并让用户确认目标 URL 和完整字段值：

```json
{
  "url": "https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01",
  "fields": {"Title": "Approved demo record", "Count": 2},
  "confirm": true
}
```

服务端在实时字段结构上验证：文本/电话、有限数值、复选框、毫秒时间戳、已有静态单选/多选和 URL。
公式、查找引用、系统、人员、关联、附件等类型的创建值会被拒绝。
不自动建字段、增加选项或修改已有记录。写入始终针对表，不限定于 view。

`confirm=true` 只是客户端对已获得用户同意的声明，不是可独立验证的人类授权证明；
不能用它替代客户端审批。需要强制审批的环境应保持写入关闭，或由可信网关先落实审批。
网络超时后写入可能已成功；服务不会自动重试写操作。先读取确认，再决定是否重试。
本版写路径只有 Mock 测试，未对真实表执行创建验收。

## 错误与可维护性

- Token 在内存缓存，带提前过期时间和并发锁；读取遇到已过期 token 时最多刷新重试一次。
- 只读 HTTP 429/部分 5xx 最多尝试三次，尊重有上限的 `Retry-After`。不自动重试写入。
- HTTP 请求有连接/总时长限制；字段和表列表有分页循环保护及页数上限。
- 飞书错误包含 HTTP 状态、code、经脱敏的 msg；不返回原始 HTTP 响应体、凭证或请求头。
  日志中不记录输入字段和凭证。调试时也不要开启会记录鉴权头的外部代理日志。
- 本项目只实现固定的 API 方法，不暴露任意 URL 请求、Raw API 或 shell 命令。

## 测试与构建

不需要飞书凭证的最小演示（两个终端）：

```bash
python examples/mock_server.py
# 另一个终端：
python examples/read_mock_table.py
```

示例 MCP 仅在 `127.0.0.1:8765/mcp` 提供虚构数据，不连接飞书。

```bash
python -m pip install '.[dev]'
ruff check src tests examples
pytest -q
python -m build
```

测试不读取 `.env`，不访问真实飞书 API。通过 HTTPX MockTransport 和 MCP 内存/ASGI 客户端验证
URL、分页、视图参数、鉴权、限流、token 刷新、错误脱敏和创建校验。字段选择和视图参数的实际飞书服务行为
仍需维护者在单独授权的测试表验证；不能把 Mock 结果当作生产集成证据。

精确依赖快照参见 `requirements-dev.lock`，其中只包含公开依赖，不包含凭证：

```bash
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps .
```

## 与官方工具的关系

[飞书官方 MCP](https://github.com/larksuite/lark-openapi-mcp)已经提供广泛的 API 工具、
多维表格能力和 Streamable HTTP；需要完整飞书工具集及其认证能力时，应优先评估官方项目。
[官方 Python SDK](https://github.com/larksuite/oapi-sdk-python)适合构建更广泛的应用。
[官方 CLI](https://github.com/larksuite/cli)也覆盖 Base、文档和电子表格。

本项目的定位是少量 URL 驱动工具、完整字段检查、可见分页和受限的单条创建策略，
便于阅读、测试和自行部署。它不替代官方平台，也不声称功能比官方工具更全。
当前直接使用公开 OpenAPI；未集成历史上评估过的 CLI 链路，不推断不同 API 之间的同名表 ID 对应关系。

许可证为 [MIT](LICENSE)。依赖许可和重新实现范围见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
贡献与安全报告参见 [CONTRIBUTING.md](CONTRIBUTING.md)、[SECURITY.md](SECURITY.md)。

## English summary

A community-maintained, small Python/FastMCP server for Feishu Bitable URLs.
It exposes four read tools and an optional, table-allowlisted `create_record` tool.
It uses tenant application credentials, preserves upstream field configuration and record fields,
and supports Streamable HTTP at `/mcp` plus local stdio. No update/delete/schema mutation tools.
Remote HTTP requires caller authentication; this project's single-owner Bearer verifier is not
an OAuth server. ChatGPT web authentication and live create/view semantics have not been verified
for this release candidate. All current automated tests use fictional data and mocked upstream APIs.
