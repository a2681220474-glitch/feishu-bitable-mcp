# 第一次接入 ChatGPT

每人使用自己的飞书应用和账号。推荐用户身份，只读。先用虚构内容测试。

## 1. 安装

下载当前源码版本并进入项目目录。需要 Python 3.11–3.13：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

Windows PowerShell 激活：`.venv\Scripts\Activate.ps1`。本项目不需要 OpenAI API Key。

## 2. 准备自己的 HTTPS 地址

ChatGPT 网页端不能直接访问你电脑的 localhost。可用服务器反向代理，或临时隧道。macOS 没有 cloudflared 时：

```bash
brew install cloudflared
cloudflared tunnel --url http://127.0.0.1:8000
```

先取得隧道 HTTPS 根地址，再配置应用。此时 MCP 尚未启动，隧道可暂时返回连接失败。已有独立部署地址可直接使用，不要改动其他服务/隧道。

虚构示例：根地址 `https://mcp.example.com`，MCP 地址 `https://mcp.example.com/mcp`。代理需转发整个服务，不能只转发 `/mcp`，OAuth 的发现、注册、同意、token 和 callback 路由也要可达。

## 3. 准备飞书应用（一次）

在 [飞书开发者后台](https://open.feishu.cn/app)创建或复用自己企业的自建应用：

1. 从「凭证与基础信息」取得 App ID、App Secret。Secret 只存本机。
2. 在权限管理开通所需的用户身份读取权限，按企业流程发布并完成管理员批准。
3. 在安全设置的重定向 URL 添加 `https://mcp.example.com/auth/callback`，换成自己的地址。
4. 确保登录用户在应用可用范围内。企业管理员可能限制创建/安装应用。

| 用途 | scope |
| --- | --- |
| 多维表格 | `bitable:app:readonly` |
| 云文档 | `docx:document:readonly` |
| 在线电子表格 | `sheets:spreadsheet:readonly` |
| 云盘 Excel 下载 | `drive:drive:readonly` |
| Wiki 解析 | `wiki:wiki:readonly` |
| 到期续期 | `offline_access` |

只开启实际需要且后台支持的读取项，并同步 `FEISHU_USER_SCOPES`。接口权限要求和企业审批为准，不能靠修改配置获得未授予的权限。

## 4. 向导配置并启动

```bash
feishu-bitable-mcp --setup
# 输入 App ID、隐藏输入的 Secret、自己的 HTTPS /mcp 地址。
# 创建私有 .env；已有文件不会覆盖。
feishu-bitable-mcp --doctor
feishu-bitable-mcp
```

也可复制 `.env.example` 后手动配置。默认 `127.0.0.1:8000`、Streamable HTTP `/mcp`。
换启动目录时用 `--env-file /absolute/path/to/.env`。已有环境变量优先于文件。
user 模式的 doctor 只做本地检查并提示浏览器登录，不证明真实凭证可用。

## 5. ChatGPT 添加并登录

1. 在自己账号的自定义 MCP/插件创建入口，填写自己的 HTTPS `/mcp` 地址，选择 OAuth。
2. 完成 MCP 同意和飞书登录授权。无需给 ChatGPT 填 App Secret。
3. 给一条测试 Base、docx、Sheets 或云盘 `.xlsx` 链接，请 ChatGPT 调用对应读取工具。

没有该入口时，检查账号/工作区功能是否支持自定义 MCP。登录、验证码和管理员审批需要本人完成。服务不依赖项目维护者的账号。

## 6. 重新授权与排错

- 过期：刷新可用时续期；失效或撤销时在 ChatGPT 重新连接、登录飞书。
- 临时域名变化：同步更新 `MCP_PUBLIC_URL`、飞书回调 URL、ChatGPT 地址。
- 权限不足：保留脱敏的 HTTP 状态/code/msg，核对 app scope、用户授权、应用可用范围和文件权限。
- 401：检查是否登录，不要通过关闭认证排查业务接口。
- 端口占用：选其他端口并同步代理目标，不要结束来源不明的服务。
- `.xls`、加密文件、宏工作簿：另存为普通 `.xlsx`；本项目不运行公式或宏。

OAuth 状态由 SDK 存到系统用户数据目录，用从 App Secret 派生的密钥加密。保留配置和状态目录以维持重启后的登录；轮换 Secret 后需重新授权。不要公开该目录、`.env`、token、业务文件或截图。

官方接口：[文档块](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/list)、[工作表](https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet/query)、[文件下载](https://open.feishu.cn/document/server-docs/drive-v1/file/download)、[用户令牌](https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token)。
