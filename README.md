# Feishu Bitable MCP

[English](README.en.md) | **简体中文** | [日本語](README.ja.md)

> **开发候选 v0.2.0rc1：** 飞书个人授权、云文档、在线电子表格及云盘 Excel 读取。模拟授权与读取测试已通过；真实飞书和 ChatGPT 浏览器验收仍待进行。已发布 v0.1.1 不包含这些新增能力。
>
> **版本说明：** 当前仅支持 Feishu 中国版。Lark 国际版使用独立 API 域名和应用凭据，尚未在本项目中实现或验证；不能仅修改名称就声称兼容。两者的品牌关系不代表凭证与数据跨区域互通。

[![CI](https://github.com/a2681220474-glitch/feishu-bitable-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/a2681220474-glitch/feishu-bitable-mcp/actions/workflows/ci.yml)

通过飞书链接读取多维表格、云文档、在线电子表格和云盘 `.xlsx` 的轻量 Python MCP 服务。
默认只读；可选开启有表白名单和字段校验的单条记录创建。

## 开源使用与配置

每人独立部署、配置自己的飞书应用和 HTTPS 服务，在 ChatGPT 添加 `/mcp` 并选择 OAuth，完成飞书本人登录授权后读取数据。无需项目维护者批准，也无需 OpenAI API Key。

用户模式使用各自的飞书权限，受应用 scope、用户同意与企业策略约束。代理支持刷新；失效时可重新登录。详见 [首次接入指南](docs/setup.md)和[授权边界](docs/user-access.md)。

## 项目初衷与功能边界

这个项目源于一个真实的使用场景：**把飞书多维表格链接直接发给 ChatGPT，让获得授权的 MCP 工具读取表结构与记录，辅助分析数据，而不必反复导出 Excel 或手工调用飞书 API。** 这是项目的目标场景，不意味着 v0.1.0 已重新完成 ChatGPT 网页端到端兼容性验证。

- **当前已实现（Feishu 中国版）：** 读取表信息、字段结构、分页记录、文档块、工作表与单元格、云盘 Excel。用户模式只读；应用身份模式可按既有保护启用单条记录创建。
- **尚未实现：** 修改已有记录、创建数据表、编辑普通飞书云文档。
- **Lark 国际版尚不支持：** 当前仅使用 `open.feishu.cn` API 与 `*.feishu.cn` Base 链接，不接受国际版域名或凭据。国际版需独立实现并验证后才能声明支持。

公开版 v0.1.0 的自动化测试使用虚拟数据和 Mock API；曾成功读写真实飞书测试表的是**较早的私有原型**，不能等同于公开版已完成生产环境验收。

这是社区项目，与飞书、Lark 或 OpenAI 没有官方隶属关系。首个公开版本为 `v0.1.0`，功能成熟度仍属早期。
原型曾在 ChatGPT 网页端完成读取及固定测试表创建；本版重新实现后以 Mock 自动化测试验证，
没有对真实飞书表执行集成读写，也没有验证当前 ChatGPT 网页端的认证流程。

## 能力与边界

| 工具 | 参数 | 行为 |
| --- | --- | --- |
| `get_bitable_info` | `url` | 返回 URL 坐标、Base 信息和精确匹配的表元数据 |
| `list_fields` | `url` | 读取全部字段页，保留原始属性，增加可读类型名 |
| `list_records` | `url, page_size=100, page_token=None` | 返回一页原始记录和下一页标记；页大小 1–500 |
| `inspect_table` | `url, sample_size=10` | 表信息、完整字段结构、主字段、API 总数和首批原始样本 |
| `resolve_resource` | `url` | 识别文档/表格/文件，解析 Wiki 指向的真实类型 |
| `read_document` | `url, page_size=100, page_token=None` | 分页原始 docx 块，保留文本、样式及树关系 |
| `get_spreadsheet_info` | `url` | 电子表格信息和全部工作表 ID/属性 |
| `read_spreadsheet` | `url, range="A1:T100", sheet_id=None, render="ToString"` | 每次最多 5000 单元格；Formula 模式读取公式 |
| `read_excel_file` | `url, sheet=None, start_row=1, rows=100, start_column=1, columns=20, data_only=false` | 云盘 .xlsx 的工作表、值/类型/数字格式与行游标 |
| `create_record` | `url, fields, confirm=false` | 默认不注册；配置允许后创建一条记录 |

- Base 工具接受 `https://*.feishu.cn/base/<app_token>?table=<table_id>`，`view` 可选。新增工具接受 `/docx/`、`/sheets/`、`/file/`、`/drive/file/` 和指向相应资源的 `/wiki/` 链接。Wiki Base 可先解析类型与 token，再使用带 table 的标准 Base URL。不支持短链接、BaseApp 和 Lark 国际版。
- 服务只从 URL 提取 ID，API 请求目的地固定为 `open.feishu.cn`。
- 读取指定视图时转发 `view_id`。实际筛选、排序和可见字段行为取决于飞书 API，
  这里仅有参数转发测试，不能将视图当成权限隔离边界。`total` 保留上游含义，未保证是视图筛选后的数量。
- 记录的所有 `fields` 和附加记录属性都会保留；不会自动概括内容。
  `inspect_table` 的首批记录不是统计抽样。
- 单次记录调用只返回一页。调用方应在 `has_more=true` 时继续传 `page_token`；不会静默只取最后一页。
- 字段中公式、查找引用、关联目标、选项等配置按飞书返回原样保留。上游未提供的配置不会推断。
- 用户模式通过飞书 OAuth 获得每个请求所属用户的凭证；兼容应用身份模式。两种身份不混用；无需安装 CLI。OAuth 状态采用 SDK 加密存储。
- 文档按 page_token 续读；嵌入图片、附件、画板等保留引用，不自动下载或渲染。
- 在线表格按显式矩形窗口读取，不声称已获取整个工作簿或完整样式。
- 云盘 Excel 限普通 .xlsx：下载 20 MiB、展开 100 MiB、窗口 5000 单元格；不执行公式/宏。data_only 读取已保存缓存，可能缺失或过期；不支持 .xls、宏工作簿、加密文件或本机路径。
- 没有更新、删除、批量写入、建表或修改字段工具。

以下 URL、字段和记录均为虚构示例，不能用于真实 API 调用：

```text
https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01&view=vewDemoView1
```

## 安装与启动

需要 Python 3.11–3.13。下载包含此 README 的源码版本并进入项目目录；当前开发候选尚未发布正式版，稳定版 v0.1.1 不含新增工具。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
feishu-bitable-mcp --setup
feishu-bitable-mcp --doctor
feishu-bitable-mcp
```

Windows PowerShell 激活：`.venv\Scripts\Activate.ps1`。向导询问自己的飞书 App ID、隐藏输入的 Secret 及公网 HTTPS `/mcp` 地址，创建私有 `.env`，不覆盖已有文件。

先按 [首次接入指南](docs/setup.md)配置飞书读取权限、应用可用范围、回调 URL 和 HTTPS；在 ChatGPT 添加地址、选择 OAuth、飞书登录。服务默认 `127.0.0.1:8000/mcp`，代理应转发整个服务。

换启动目录可用 `--env-file /absolute/path/to/.env`；环境变量优先。用户模式 doctor 只验证本地配置，实际 API 权限须在登录后的工具调用中验证。

应用身份兼容模式设置 `FEISHU_AUTH_MODE=app`，给应用目标资源权限。静态 Bearer HTTP 客户端配置至少 32 字符 `MCP_AUTH_TOKEN`；非回环监听必须有鉴权。临时 HTTPS 隧道也会暴露回环端口，应先配置鉴权。应用模式也支持 `--transport stdio`。ChatGPT 登录与回调说明见 [OAuth 接入](docs/chatgpt.md)。

`FEISHU_READ_TABLE_URLS` 可限制 Base 表；`FEISHU_READ_RESOURCE_URLS` 可限制新工具的资源链接，逗号分隔。空列表表示身份自身已获授权的范围，不会绕过飞书权限。

## 可选：创建一条记录

用户模式只读。应用身份模式默认也不含 `create_record`；操作者须同时设置：

```dotenv
FEISHU_AUTH_MODE=app
MCP_PUBLIC_URL=
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
- 读取遇到暂时性网络失败、HTTP 429/部分 5xx 最多尝试三次，使用带抖动的退避。
  `Retry-After` 超过 5 秒时直接返回上游错误，交由调用方稍后重试，不提前重发请求。
  不自动重试写入或获取 token 的 POST 请求。
- 每次 HTTP 尝试最多 20 秒（含并发排队），同一客户端最多四个请求同时在途；工具总预算为 90 秒。
  字段和表列表有分页循环保护及页数上限。
- 飞书错误包含 HTTP 状态、code、经脱敏的 msg；不返回原始 HTTP 响应体、凭证或请求头。
  日志中不记录输入字段和凭证。调试时也不要开启会记录鉴权头的外部代理日志。
- 创建校验错误会指出字段名与预期格式，不回显提交值；字段名截断至 120 字符并转义控制字符。
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

CI 同时验证哈希锁定安装和 `.[dev]` 独立解析安装，并运行 `pip check`。
每周一另有定期验证和依赖漏洞审计；升级依赖时须同步更新锁文件，流程见 [CONTRIBUTING](CONTRIBUTING.md)。

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

A self-hosted Python/FastMCP service for Feishu Bitable, docx documents, online spreadsheets and uploaded .xlsx files. Nine read tools preserve raw pages and explicit read windows. Feishu user OAuth is available in the development candidate; app identity and guarded optional record creation remain compatible. Streamable HTTP uses `/mcp`. Full synthetic consent/PKCE/read/refresh/revocation tests pass; live Feishu/ChatGPT browser acceptance is pending. See [English README](README.en.md).
