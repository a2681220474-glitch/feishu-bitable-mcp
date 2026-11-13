# ChatGPT 网页端接入（外部 OAuth）

个人使用优先选择 [GitHub 登录](github-login.md)，无需额外身份服务。本页针对已有企业身份服务的高级配置。

本分支提供 OAuth **资源服务器**能力：公布受保护资源元数据，并验证外部身份服务签发的 RS256 JWT。授权码、登录页面、用户同意、刷新令牌由你的身份服务处理。本项目不保管用户 refresh token，不把 MCP 登录转换成飞书个人身份；上游仍使用自建应用身份。

当前已用虚构密钥/令牌验证本地协议及拒绝边界；**尚未完成真实身份服务与 ChatGPT 浏览器授权验收**。下列是配置和验收步骤，不能视为已验证的即插即用部署方案。

## 前提与身份服务

使用一个符合 [OpenAI OAuth 要求](https://developers.openai.com/plugins/build/auth)的成熟身份服务：支持授权码 + PKCE S256、OAuth 元数据、ChatGPT 支持的客户端注册方式（CIMD、DCR 或预注册客户端），并为你的 MCP 资源签发访问 token。

本集成只接受 RS256 JWT，要求：有效签名、`iss` 与配置完全相同、`aud` 包含 MCP 完整公网 `/mcp` URL、有效 `exp`、非空 `sub`、`read` scope，以及满足可选 `nbf`。**不能把 Google ID token、飞书 tenant token 或任意其他受众的 token 当作 MCP access token。**

在身份服务端把登录和资源授权限制为维护者/明确允许的用户；若允许公开注册并自动授予 `read`，这些人会获得同一飞书应用及服务白名单允许的资源访问能力。此版本不提供逐用户飞书权限隔离，推荐每位使用者各自部署。

## 配置

以下域名都是虚构样例，替换为自己身份服务控制台的真实配置：

```dotenv
FEISHU_APP_ID=<your-app-id>
FEISHU_APP_SECRET=<your-app-secret>
FEISHU_ENABLE_WRITES=false
FEISHU_READ_TABLE_URLS=<authorized-test-table-url>
MCP_AUTH_TOKEN=
MCP_OAUTH_ISSUER=https://identity.example.com/
MCP_OAUTH_JWKS_URL=https://identity.example.com/.well-known/jwks.json
MCP_PUBLIC_URL=https://mcp.example.com/mcp
```

issuer 的结尾斜杠须和 JWT `iss` 保持一致。JWKS 地址必须来自你的身份服务；设置不会由 MCP 客户端参数改变。JWT audience 固定为 `MCP_PUBLIC_URL`，无需额外配置。这个 OAuth 模式保持只读，不能与静态 MCP_AUTH_TOKEN 或可选写入混用。

```bash
feishu-bitable-mcp --env-file /absolute/path/to/.env --doctor
feishu-bitable-mcp --env-file /absolute/path/to/.env --doctor --url '<test-table-url>'
feishu-bitable-mcp --env-file /absolute/path/to/.env
```

把自己的 HTTPS 反向代理转发到 `127.0.0.1:8000`，保留 `/mcp`、`/.well-known/oauth-protected-resource/mcp` 路径及 Authorization 头。已有正常 tunnel 无需重建；临时域名变化后需要同时更新 public URL、身份服务 audience 和 ChatGPT 连接配置。

## 检查与连接

```bash
curl https://mcp.example.com/.well-known/oauth-protected-resource/mcp
```

应返回 `resource=https://mcp.example.com/mcp`、配置的 `authorization_servers` 与 `scopes_supported`。未带有效凭证访问 `/mcp` 应返回 401，WWW-Authenticate 头指向上述 metadata。

在 ChatGPT 的自定义 MCP 创建入口填写完整 `https://mcp.example.com/mcp`，选择 OAuth。按身份服务支持方式配置客户端；需要预注册时，将 ChatGPT 管理页面显示的**准确回调地址**加入身份服务 allowlist，不能凭旧教程猜测。亲自完成浏览器登录和同意后，刷新工具，确认只出现四个读取工具。

首次只给测试表 URL，调用 inspect_table；然后用 list_records 验证分页和视图范围。身份服务、ChatGPT 权限或验证码需要使用者本人处理。

## 发布前仍需真人验收

- 从另一账号/浏览器按文档配置，完成登录、工具发现、一次真实测试表读取。
- 撤销授权、访问令牌过期和重新授权可正常处理；检查拒绝未允许用户。
- 验证真实视图筛选/排序和跨页结果，而非只确认 MCP 握手成功。

依据：[OpenAI Authentication](https://developers.openai.com/plugins/build/auth)、[FastMCP Remote OAuth](https://gofastmcp.com/servers/auth/remote-oauth)。使用不支持上述注册方式或无法签发对应 JWT 的身份服务时，需要适配层，不能只填写这三个 URL 就保证兼容。
