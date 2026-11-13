# 首次配置与故障排查

先使用自己创建的飞书企业自建应用，以及只包含虚构数据的测试 Base。不要把 App Secret 发给维护者。

## 1. 配置飞书

1. 在 [开发者后台](https://open.feishu.cn/app)创建/打开企业自建应用，从「凭证与基础信息」获取 App ID、App Secret，写入自己的 `.env`。
2. 在「权限管理」为下面四个读取 API 开通所需权限；按对应接口文档的「权限要求」选择读取项。根据租户流程发布应用并完成管理员批准。不要为只读接入申请编辑或管理权限。
3. 在目标 Base 的分享/协作者/应用访问设置中，把该自建应用加入可访问范围，给予读取权限。界面名称随租户版本变化；如果应用不可选，请联系 Base 所有者或企业管理员。
4. 复制标准 `https://<tenant>.feishu.cn/base/<token>?table=<id>` 链接；可保留 `view=`。Wiki、短链接和国际版 Lark 不受支持。

| 自检步骤 | 调用接口 | 官方权限与响应说明 |
| --- | --- | --- |
| tenant_authentication | 获取企业应用 token | [获取 tenant_access_token](https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal) |
| base_and_table_access | 获取 Base 信息、列出数据表 | [Base 信息](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app/get)、[数据表列表](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table/list) |
| fields_access | 列出字段 | [字段列表](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-field/list) |
| records_access | 读取一条记录 | [记录列表](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list) |

部分权限在后台可通过 `bitable:app:readonly` 搜索。细粒度权限应按以上接口当前列出的读取要求配置；不要假设开通任意一项就覆盖全部四个读取工具。API scope 与 Base 资源授权都需要满足。

## 2. 先自检，再接客户端

```bash
# 不调用飞书，只检查本地配置；环境变量优先于文件。
feishu-bitable-mcp --env-file /absolute/path/to/.env --doctor

# 明确给出授权测试表后，才向飞书认证并发起只读 API 调用。
feishu-bitable-mcp --env-file /absolute/path/to/.env --doctor --url '<test-table-url>'

# 使用同一配置启动；无需切换到项目目录。
feishu-bitable-mcp --env-file /absolute/path/to/.env
```

成功退出码为 0，检查失败为 1，CLI 参数错误为 2。JSON 包含每个阶段的状态，遇到失败停止后续 API 检查；不会输出字段名、表内容、访问 token 或 Secret。带 `--url` 的总检查预算为 75 秒；无 URL 的本地检查不证明真实凭证可用，也不验证远程 OAuth 登录。

## 3. 按失败阶段处理

| 现象 | 下一步 |
| --- | --- |
| configuration | 检查 `.env` 中必填项、白名单 URL 和鉴权配置；检查是否有旧的环境变量覆盖文件。 |
| target | 从浏览器复制完整 /base/ URL；检查表是否在读取白名单内。 |
| tenant_authentication | 在开发者后台核对同一个应用的 ID/Secret；如已轮换凭证，更新后重试。 |
| base_and_table_access / fields_access / records_access | 保留脱敏的 HTTP 状态、code 与 msg；按接口核对 scope、应用发布状态、Base 资源授权及高级权限。 |
| 网络错误 / 429 / 5xx | 检查网络，按上游提示稍后重试；不要通过反复并发调用绕过限流。 |
| 启动报告端口已占用 | 使用 `--port 8001` 并同步修改客户端/代理转发地址；不要结束来源不明的服务。 |
| ChatGPT 无法登录或发现工具 | 按 [ChatGPT 配置](chatgpt.md)检查 HTTPS、OAuth 发现文档、PKCE、回调地址、JWT 的 issuer/audience/read scope。 |

发 issue 时只提供版本、Python/系统、客户端、失败阶段及脱敏错误。不要附上 `.env`、令牌、真实表链接或数据截图。
