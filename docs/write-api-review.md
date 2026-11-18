# 写接口与 Scope 核对

2026-11-18 补充：[真实接口验收](live-validation.md)确认了细粒度用户授权下的 Base v3 读取及 Sheets 写权限兼容。
`sheets:spreadsheet:write_only` 已验证可用于本项目现有工作表、值、追加和样式操作；公开接口页仍列旧的宽权限，以下表格保留其原始声明。

核对日期：2026-11-17。来源为飞书官方 [Markdown 文档索引](https://open.feishu.cn/llms-docs/zh-CN/llms-docs.txt) 对应的完整接口页，以及官方 CLI 的实际源码。
下列路径均在 `https://open.feishu.cn/open-apis` 下；Scope 列为可选其一，不能把本地允许列表等同于飞书授予。
支持 tenant_access_token / user_access_token 的文档接口均保留两种显式身份；无降级回退。

| 操作 | HTTP 与路径 | 候选写 Scope（任一） | 官方依据 |
| --- | --- | --- | --- |
| 创建 Base | POST `/bitable/v1/apps` | `base:app:create` / `bitable:app` | [创建 Base](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app/create.md) |
| 创建数据表 | POST `/bitable/v1/apps/{app}/tables` | `base:table:create` / `bitable:app` | [创建表](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table/create.md) |
| 创建字段 | POST `/bitable/v1/apps/{app}/tables/{table}/fields` | `base:field:create` / `bitable:app` | [创建字段](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-field/create.md) |
| 新增记录 | POST `/bitable/v1/apps/{app}/tables/{table}/records/batch_create` | `base:record:create` / `bitable:app` | [批量新增](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/batch_create.md)；UUIDv4 client_token |
| 修改记录 | POST `/bitable/v1/apps/{app}/tables/{table}/records/batch_update` | `base:record:update` / `bitable:app` | [批量更新](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/batch_update.md) |
| 创建文档 | POST `/docx/v1/documents` | `docx:document:create` / `docx:document` | [创建文档](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/create.md) |
| 插入段落 | POST `/docx/v1/documents/{doc}/blocks/{parent}/children` | `docx:document:write_only` / `docx:document` | [创建块](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/create.md)；1–50 子块、index、revision、client_token |
| 修改文本块 | PATCH `/docx/v1/documents/{doc}/blocks/{block}` | 同上 | [更新块](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/patch.md)；只封装 update_text_elements |
| 创建在线表格 | POST `/sheets/v3/spreadsheets` | `sheets:spreadsheet:create` / `sheets:spreadsheet` / `drive:drive` | [创建表格](https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet/create.md) |
| 新增工作表 | POST `/sheets/v2/spreadsheets/{token}/sheets_batch_update` | `sheets:spreadsheet` / `drive:drive` | [工作表操作](https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet/operate-sheets.md)；适配器仅允许 addSheet |
| 写值/公式 | PUT `/sheets/v2/spreadsheets/{token}/values` | 同上 | [写范围](https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/write-data-to-a-single-range.md)、[公式类型](https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-types-supported-by-sheets.md) |
| 追加数据 | POST `/sheets/v2/spreadsheets/{token}/values_append` | 同上 | [追加](https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/append-data.md)；显式 INSERT_ROWS |
| 基础格式 | PUT `/sheets/v2/spreadsheets/{token}/style` | 同上 | [样式](https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/set-cell-style.md) |
| 上传 XLSX | POST multipart `/drive/v1/files/upload_all` | `drive:file:upload` / `drive:file` / `drive:drive` | [上传](https://open.feishu.cn/document/server-docs/docs/drive-v1/upload/upload_all.md)；上限 20 MiB |

Scope 是接口级要求；同一个 Scope 不一定意味着用户拥有目标文件的编辑权。飞书仍检查资源 ACL、企业策略及应用配置。
读取预检还需字段、记录、Docx、Sheets、文件下载等对应读取权限；默认只读 Scope 可按实际需求保留。
本地新增权限开关/URL 白名单/确认不能绕过以上任一层。
完整授权链路的模拟测试涵盖 token 响应缺失 scope、部分授予、刷新及用户隔离，未替代真实租户验收。

## XLSX 覆盖证据与限制

公开 `upload_all` 参数表未列出 file_token，但 [官方 CLI 的固定源码](https://github.com/larksuite/cli/blob/8a7fa53355d5ec27df06ec8b36152ca7c35919fc/shortcuts/drive/drive_upload.go) 明确提供 `--file-token` 并在 multipart 上传中加入该字段。
适配器实现同样的传输，并核对返回 token 等于原文件；同 token 覆盖已在虚构样本验收，仍必须额外配置目录才启用实验性覆盖。
不会执行 CLI 中可能存在的后续自动 ACL 授权步骤，也不会修改已有文件权限。

[创建文档版本](https://open.feishu.cn/document/server-docs/docs/drive-v1/file-version/create.md) 的 obj_type 只列 docx / sheet，不适用于上传的 XLSX。
因此本项目不调用该接口来冒充 Excel 文件新版本，不声称上传响应包含已验证的版本历史 ID。

## 并发和功能覆盖结论

上述 API 文档未给出本项目可据以证明严格原子 CAS 的机制；Docx 的旧 revision 在一定范围内仍可接受，不能当数据库版本锁。
实现的是提交前快照比较、本地持久租约及不确定结果停写。外部并发编辑仍有窗口。
公式、复杂格式、人员/附件/关联写值、复杂文档块等超出当前保守适配范围的能力会明确拒绝，不用 Mock 结果冒充已实现或已通过真实 API 验收。
