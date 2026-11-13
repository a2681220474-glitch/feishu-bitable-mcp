# ChatGPT 与飞书本人授权

推荐流程见 [首次接入指南](setup.md)。使用者配置自己的飞书自建应用和 HTTPS 服务，在 ChatGPT 添加自己的 `/mcp` URL 并选择 OAuth，然后在飞书登录并同意读取。

底层使用 FastMCP OAuthProxy：客户端发现和注册、同意页面、PKCE、授权码交换、加密持久化和刷新由 SDK 处理；本项目适配飞书 JSON token 端点及用户信息验证。原始飞书令牌只在服务端使用。

服务应完整转发 `/.well-known/*`、`/authorize`、`/token`、`/register`、同意页面和 `/auth/callback`，以及 `/mcp`。只转发 `/mcp` 会使登录失败。

飞书应用的回调填写自己服务的 `/auth/callback`。ChatGPT 客户端回调由 SDK 处理，并限制在 ChatGPT 域名，不能把两个回调地址混淆。

自动刷新失效、用户撤销或企业策略变化时，在 ChatGPT 重新连接并登录；代码不会改用应用身份读取。用户模式的工具全部只读，实际数据范围由飞书权限控制。

## 验证与限制

模拟测试覆盖完整客户端授权、同意、PKCE、MCP 读取、刷新、撤销后拒绝和并发身份隔离。真实飞书/ChatGPT 浏览器验收待完成。仅服务启动或 doctor 配置检查通过，不能视为真实授权成功。

参考：[OpenAI Authentication](https://developers.openai.com/plugins/build/auth)、[FastMCP OAuth Proxy](https://gofastmcp.com/servers/auth/oauth-proxy)、[飞书用户凭证](https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token)。
