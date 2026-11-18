# 预览、确认与写入（开发分支）

本功能尚未发布；现有 `v0.2.0-rc.1` 安装包不包含本页新增操作。
已通过 Mock 测试，并于 2026-11-18 在专用资源上完成真实业务接口验证；方法、认证边界与结果见[验收摘要](live-validation.md)。新版 ChatGPT 网页 OAuth 仍待独立验收。
默认只读。不开启新配置时，原有读取工具及接入流程不变。

## 配置

先按 [接入指南](setup.md)部署自己的应用和 HTTPS 服务。不要把个人凭证发给项目维护者。
在私有 `.env` 中按需启用操作和**精确资源 URL**，以下全部是虚构示例：

```dotenv
FEISHU_AUTH_MODE=user
FEISHU_ENABLE_WRITES=false
FEISHU_ENABLE_CHANGES=true
FEISHU_CHANGE_LEDGER=.state/operations.sqlite3
FEISHU_CHANGE_ALLOWLIST='{"bitable.create_records":["https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01"],"document.insert_text":["https://example.feishu.cn/docx/DocxDemoToken0001"],"sheets.write_cells":["https://example.feishu.cn/sheets/SheetDemoToken01?sheet=demo01"]}'
FEISHU_USER_SCOPES=bitable:app:readonly base:record:create docx:document:readonly docx:document:write_only sheets:spreadsheet drive:drive:readonly offline_access
```

只申请需要的 Scope，并在飞书应用权限、发布版本/可用范围及个人登录同意中实际获得它们。
**修改本地配置不能获得飞书权限。** 代理从实际 token 响应的 `scope` 读取授予证据；缺失、不足或撤销时拒绝写入，不用请求 Scope 冒充授权，也不回退到应用 Token。
预览为了验证字段、旧值、版本或文件，还需要相应读取权限；API 报错包含脱敏后的 code/msg。
如果设置了读取 URL 白名单，既有资源的写入预检也必须在其范围内；写入白名单不能绕过读取策略。
准确接口与候选 Scope 见 [API 核对](write-api-review.md)，每个操作只需其中一个写 Scope，另加必要读取权限。

应用模式也可使用相同操作，但须设置 `FEISHU_AUTH_MODE=app` 和强 `MCP_AUTH_TOKEN`，实际由飞书检查应用的权限与目标 ACL。
`FEISHU_ENABLE_WRITES` 是旧版单条 `create_record` 的兼容开关，不能与新模式同时启用。
新模式不注册旧写入工具，只注册 `prepare_change`、`commit_change`、`get_change_status`。
旧模式没有本页的持久回执保证；新部署推荐使用新流程，保持兼容开关关闭。

URL 的域名与路径严格检查，请求始终发到固定飞书 API，不抓取 URL 本身。
新增/修改仅接受直接 `/base/`、`/docx/`、`/sheets/`、`/file/` 和 `/drive/folder/` URL；不沿 Wiki 间接授权写入。
表的 `view` 不构成写入权限边界；写入对象仍是数据表。在线表格白名单带 `sheet=` 时，调用参数不能跳到另一工作表。
创建 Base/文档/在线表格/Excel 必须明确授权其目标文件夹；新资源不会自动加入修改白名单。

## 调用方式

1. `prepare_change(operation, url, payload, request_id)`：仅读取预检；返回精确内容、目标、快照条件、摘要和 10 分钟有效的 plan_id。
2. 展示内容和副作用，取得用户明确同意。读取到的文档、单元格或提示文本不能代替用户确认。
3. `commit_change(plan_id, confirmation_digest, confirm=true)`：只执行该用户的这份预览，重新检查 Scope、策略和快照。
4. `get_change_status(request_id)`：查看自己的回执。重试必须保持同一个 request_id；不能换 ID 掩盖不确定结果。

`confirm=true` 是客户端的确认声明，服务器无法由一个布尔值证明真人点击。
要强制真人审核，必须让可信客户端/网关实施确认；不要在 ChatGPT 中为写工具启用无人审阅的自动执行。

例如只新增一条多维表格记录：

```json
{
  "operation": "bitable.create_records",
  "url": "https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01",
  "payload": {"records": [{"fields": {"Title": "Approved example"}}]},
  "request_id": "example-create-0001"
}
```

`request_id` 用 8–100 个字母、数字、下划线或连字符，不包含业务正文、邮箱或凭证。

## 操作与 payload

| operation | 目标 URL | payload 与边界 |
| --- | --- | --- |
| `bitable.create_records` | 表 | `{"records":[{"fields":{"Title":"Example"}}]}`；1–100 条，包括单条 |
| `bitable.update_records` | 表 | `{"records":[{"record_id":"recDemoRecord01","fields":{"Title":"Changed"}}]}`；只修改提交的字段，1–100 条 |
| `bitable.create_base` | 文件夹 | `{"name":"Demo"}` |
| `bitable.create_table` | 无 table/view 的 Base URL | `{"name":"Table","fields":[{"field_name":"Title","type":1}]}`；fields 可省略 |
| `bitable.create_field` | 表 | `{"field_name":"Status","type":3,"property":{"options":[{"name":"New"}]}}` |
| `document.create` | 文件夹 | `{"title":"Demo document"}`；先创建空文档 |
| `document.insert_text` | docx | `{"paragraphs":["First","Second"],"parent_block_id":"BlockDemoToken01","index":0}`；父块默认文档根，index=-1 追加；1–50 个纯文本段落 |
| `document.replace_text` | docx | `{"block_id":"BlockDemoToken01","text":"Replacement"}`；只替换 type=2 纯文本块，其原行内格式会被替换 |
| `sheets.create` | 文件夹 | `{"title":"Demo spreadsheet"}` |
| `sheets.add_worksheet` | 不带 sheet= 的工作簿 | `{"title":"Data","index":0}`；index 可省略，只封装 addSheet |
| `sheets.write_cells` | 在线表格 | `{"sheet_id":"demo01","range":"A1:B1","values":[[2,{"type":"formula","text":"=A1*2"}]]}`；矩阵精确填满矩形 |
| `sheets.append_cells` | 在线表格 | 同上，矩形可以比数据大；固定 INSERT_ROWS，会移动下方单元格，不使用默认覆盖追加 |
| `sheets.format_cells` | 在线表格 | `{"sheet_id":"demo01","range":"A1:B1","style":{"font":{"bold":true},"backColor":"#FFFF00"}}` |
| `excel.create` | 文件夹 | `{"file_name":"Demo.xlsx","worksheets":[{"name":"Data","values":[[1,2]]}]}`；新工作簿 1–20 页，总计最多 5000 格 |
| `excel.edit` | 精确文件 URL | `{"file_name":"Demo.xlsx","cells":[{"sheet":"Data","cell":"B2","value":3}]}`；1–5000 个明确单元格；实验性覆盖须额外配置 |

多维表格写值支持文本、电话、数值、静态单/多选、日期、复选框和 URL，按实时结构校验；不自动增加选项，不写系统、公式、关联、附件和人员字段，不以 null 清空字段。
创建字段仅开放 type `1/2/3/4/5/7/13/15`，property 目前仅支持单/多选的命名选项。不是完整 Base 重建或复杂公式字段创建器。

在线表格每次最多 100 列、5000 格。值支持 null、布尔、有限数值、文本和显式公式对象。
以 `=` 开头的普通字符串会被拒绝，公式必须用 `{"type":"formula","text":"=..."}`，不会在本机计算。
基本格式仅支持 font.bold/italic/fontSize、formatter、hAlign/vAlign、foreColor/backColor。
文档本轮仅开放纯文本块；不伪装支持图片、画板和任意嵌套复杂块编辑。
没有删除记录、删除表/块/文件工具，也不开放 Raw API、shell 或任意路径。

## XLSX 保存与覆盖的边界

普通 XLSX 最大 20 MiB、展开最大 100 MiB。编辑不通过整本 openpyxl 重新保存，而是局部替换 OOXML 单元格并复制其他 ZIP 条目。
Mock 及真实上传的虚构工作簿均已核对：未修改工作表、图表、样式等 ZIP 条目的解压内容不变；保留目标格 style 属性、其他格公式、合并与冻结设置。
修改目标格会替换其值/富文本；公式缓存需重新计算，不承诺所有第三方扩展或工作簿都可编辑。
拒绝 XLS、加密/宏/签名/保护工作簿、目标工作表中的共享/数组/data-table 公式、合并区非左上格；含 calcChain 时拒绝公式单元格修改。
本机不执行公式或宏。修改后标记全量重算，其他公式的已保存缓存可能仍旧，须用 Excel 重算。

`excel.edit` 还要求操作者设置私有配置：

```dotenv
FEISHU_EXCEL_OVERWRITE_FOLDER_URL=https://example.feishu.cn/drive/folder/DemoFolderToken01
```

这是上传接口需要的明确目标目录，必须是已授权测试文件所在目录；不能让客户端替换该目录。
覆盖沿用官方 CLI 发送 `file_token` 的实现；飞书公开 upload_all 参数表未完整列出该参数，所以保留实验标记。已在专用虚构 XLSX 上验证同 token 覆盖与回读，不代表所有工作簿兼容。
返回 token 必须与原文件相同，否则结果记为不确定并停止，不把新副本冒充覆盖成功。
该路径不是 `files/{token}/versions` 文档版本 API，不保证生成可列举的版本号或自动备份。
启用前请用独立测试文件验证文件名、目录、版本行为和保留内容，再考虑生产用途。

## 超时、并发与故障恢复

SQLite 回执先于请求写盘；同一个用户/request_id 永久绑定同一操作与内容摘要。
同一资源只派发一个操作；在线表格按整个工作簿串行化。重复 commit 读取已有回执，不再次发送请求。
执行前重新读取字段、记录/文档 revision/单元格窗口或 XLSX SHA256。
这些 API 没有已验证的严格原子 CAS；**快照检查后外部人员仍可能编辑**。避免同时编辑同一目标，生产场景需另加协作窗口。
格式预检覆盖单元格值及工作表元数据，不能探测全部格式变更。
文档 revision 参数不当作严格锁；已核对的接口甚至允许一定范围的旧版本。

写请求不自动重试。已派发后的异常，包括格式不完整的响应，保守标记 `unknown`；崩溃留下 `started`。
两者持有资源租约，重启也不会自动解锁或过期。确定失败的预检记为 conflict，可用新请求重新预览。
`.state/` 是私有持久状态，不得公开或当缓存删除；备份应保留回执与 OAuth 加密状态，禁止复用同一请求到不同独立账本。
预览存在进程内；重启或路由到另一 worker 时需要重新预览，已派发请求的回执仍持久保留。
当前推荐单个服务进程和本地持久磁盘，尚未提供多副本/网络文件系统支持。

不确定结果必须由运营者先停止所有 worker，直接检查飞书实际结果，保存私有证据，再用本地工具处理。
此工具不暴露给 MCP，也不获取/打印任何 Token：

```bash
python -m feishu_bitable_mcp.change_store --ledger .state/operations.sqlite3
# 只有本人核实远端实际结果且停止所有进程后：
python -m feishu_bitable_mcp.change_store --ledger .state/operations.sqlite3 \
  --owner <上一步返回的owner哈希> --request-id <request_id> \
  --outcome verified_applied --evidence-sha256 <私有核对证据的SHA256> \
  --confirm-all-workers-stopped
```

未生效使用 `verified_not_applied`。核对会保留原 request_id 的终态记录，只解除资源租约，不把旧请求重新变成可发送。
不要在结果无法确认时强行解锁或改用新 ID。审计库记录身份/资源/内容哈希、时间、状态和必要结果 ID，不保存正文和凭证。
