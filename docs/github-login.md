# 部署者可选的 GitHub 访问控制

这个方案让 ChatGPT 打开 GitHub 登录页面确认身份。无需另注册 Auth0/Descope；飞书访问仍使用你自己的企业自建应用。底层采用 FastMCP 的 GitHubProvider，不自行实现密码或授权协议。

这是某个部署实例的访问控制，不是使用开源代码的许可要求，也不授予飞书个人数据权限。
白名单由该实例的部署者管理。项目维护者不会审批他人的独立部署。
首次使用请先阅读 [使用方式与授权边界](user-access.md)。

**目前已验证本地 OAuth 元数据、PKCE 声明和用户白名单边界；真实 GitHub/ChatGPT 浏览器授权尚待验收。**

## 你只需准备一次 GitHub OAuth App

1. 确认自己 MCP 的公网 HTTPS 地址，例如虚构的 `https://mcp.example.com/mcp`。已有正常 tunnel 不需重建。
2. 打开 [GitHub OAuth Apps](https://github.com/settings/developers)，点击 **New OAuth App**。这不会修改飞书应用或现有 GitHub 仓库。
3. Application name 填 `Feishu Bitable MCP`；Homepage URL 填自己的 MCP 根地址 `https://mcp.example.com`；Authorization callback URL 填 `https://mcp.example.com/auth/callback`。
4. 点击 Register application。复制 Client ID；点击 Generate a new client secret，把 Secret 直接保存在本机 `.env`，不要发到聊天或 issue。
5. 查看自己 GitHub 的数值 ID：在浏览器打开 `https://api.github.com/users/<your-github-username>`，读取 `id`。使用数值 ID 防止账号改名造成授权混淆。

## `.env` 配置

```dotenv
FEISHU_APP_ID=<your-feishu-app-id>
FEISHU_APP_SECRET=<your-feishu-app-secret>
FEISHU_ENABLE_WRITES=false
FEISHU_READ_TABLE_URLS=<authorized-test-table-url>
MCP_AUTH_TOKEN=
MCP_OAUTH_ISSUER=
MCP_OAUTH_JWKS_URL=
MCP_PUBLIC_URL=https://mcp.example.com/mcp
MCP_GITHUB_CLIENT_ID=<your-github-oauth-client-id>
MCP_GITHUB_CLIENT_SECRET=<your-github-oauth-client-secret>
MCP_GITHUB_ALLOWED_USER_IDS=<your-numeric-github-user-id>
```

多个明确批准的用户数值 ID 用英文逗号分隔。未列入白名单的 GitHub 用户即使登录，也无法调用 MCP。所有获准用户共享服务中飞书应用与表白名单的范围；推荐每位朋友使用自己的部署，避免共享公司资源。

默认只申请 GitHub `read:user`，用于确认基本账号身份，不申请仓库写权限。授权过程保留 FastMCP 同意页面；只允许 ChatGPT 域名的客户端回调。GitHub OAuth App 的回调是 MCP 自己的 `/auth/callback`，与 ChatGPT 客户端回调不是同一个地址。

## 启动与验证

先按 [配置自检指南](setup.md)检查测试表访问，再启动：

```bash
feishu-bitable-mcp --env-file /absolute/path/to/.env --doctor
feishu-bitable-mcp --env-file /absolute/path/to/.env
```

HTTPS 代理需转发整个服务，包括 `/mcp`、`/.well-known/*`、`/authorize`、`/token`、`/register` 和 `/auth/callback`。不能只转发 `/mcp`。在 ChatGPT 添加完整公网 `/mcp` URL，选择 OAuth；客户端注册由 FastMCP 代理提供，无需把 GitHub Client Secret 填进 ChatGPT。

首次连接完成同意页面和 GitHub 授权后，用授权测试表调用 inspect_table。正式开放给朋友前，还须验证令牌过期/刷新、服务重启后重新连接，以及未允许账号不能读取。

FastMCP 默认把 OAuth 状态存到系统用户数据目录下的 `oauth-proxy` 子目录，具体位置由系统和 FastMCP 配置决定，用从 GitHub Client Secret 派生的密钥加密。该目录和 `.env` 都不能提交或分享。稳定保留 Secret 与数据目录能避免重启后丢失登录状态；轮换 Secret 后需重新授权。本地 `--doctor` 不创建 OAuth 状态库。详细行为见 [FastMCP GitHub OAuth 文档](https://gofastmcp.com/integrations/github)。
