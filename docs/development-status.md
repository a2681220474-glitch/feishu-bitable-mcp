# 开发交接：四类资源写入（更新于 2026-11-18）

分支：`maintenance/onboarding-reliability`；沿用 PR #9，保持 draft。
起点：`a8770c18570d89595b607b0e603b4c8d4479ca8a`（原候选 `0.2.0rc1`）。
未合并 main，未替换任何已发布版本，未部署到原服务，也未重建 HTTPS 隧道。

## 已落地

- 保留九个读取工具；新写入默认关闭，新增 prepare_change / commit_change / get_change_status。
- 15 个具名操作覆盖 Bitable 基础创建/记录新增修改、Docx 创建及纯文本块、Sheets 创建及基础读写格式、XLSX 创建及受限单元格覆盖。
- 实际 OAuth grant 检查、个人/应用身份隔离、读取与操作白名单交集、精确 worksheet 限制。
- 明确确认摘要、10 分钟预览、提交前快照、私有 SQLite 回执、跨进程资源租约、不确定结果停写、离线人工核对工具。
- XLSX 局部 OOXML 修改和无关 ZIP 条目保留；不支持的结构在上传前拒绝。
- 官方接口/Scope 核对、三语言说明同步、私有配置示例和故障恢复文档。

## 当前验证

本地 Python 3.12 下 350 项 Mock 测试通过；不依赖飞书凭证。
首次推送的六个功能/跨平台 CI job 通过；依赖审计发现旧锁文件的两项新公告，已按修补版本更新 dnspython 及 opentelemetry-api，并为普通安装设置版本下限。安全修复后的 CI 结果见最新检查。
完整模拟覆盖 OAuth 注册/同意/PKCE、授权码及刷新、Scope 缺失/部分授予、不同用户并发写入的 Token 隔离、MCP 预览/确认/回执链路、重启防重复、未知结果租约和资源冲突。
XLSX 测试回读修改结果，并逐个核对无关 ZIP 条目，包含图表、样式、未改公式和其他工作表。
2026-11-18 在维护者明确授权的测试 Wiki 资源与新建测试目录中，通过 CLI 本人授权传输桥调用真实接口：15 种操作、18 次成功变更及回读；没有删除请求，收尾无不确定回执。
XLSX 同 token 覆盖、图表/样式等保留已在虚构样本验证；3 条记录的 2+1 分页和在线公式零错误自检通过。
没有更改应用权限、导出原始 Token 或动原服务。验收桥只用于测试，不是多用户产品后端；方法见 [live-validation.md](live-validation.md)。
安装包验证及 PR CI 的最新结果以交付报告和 GitHub 检查为准。

## 尚待完成的验收

1. 真实接口的现有用户授权验证已完成；仍需独立验收公开服务的新 OAuth 同意、刷新、撤销与用户隔离，不复用测试桥冒充认证网关成功。
2. 从 ChatGPT 网页端实测预览、拒绝、确认、超时后查询、撤销和重新授权，不以 Mock 冒充端到端结果。
3. XLSX 同 token 上传及内容保留已通过虚构样本验收；版本历史/版本号行为仍未验证，额外配置默认关闭。
4. 根据实际需求再扩展高级字段/复杂块；目前仅文档纯文本，不能称为任意文档深度编辑或完整 Base 重建。
5. 外部编辑仍可能发生竞态；快照与 revision 参数不提供严格原子 CAS。更严格场景需协作窗口或产品层冲突方案。
6. 评估移除旧 create_record 兼容路径的迁移计划；新模式已禁止与旧开关同时开启。
7. 上述真实验收通过后再确定新版本号、更新发布材料、解除 draft 和合并；不覆盖旧 rc1 发布资产。

## 继续开发

复用现有 Python 环境；确保 import 指向工作区代码，而不是环境中先前安装的旧 wheel：

```bash
git status --short --branch
git log -1 --oneline
ruff check src tests examples
PYTHONPATH=src python -m pytest -q
python -m build
```

写入主入口在 `changes.py`，操作/目标/Scope 表在 `change_policy.py`，各类协议在对应 `*_changes.py`。
接口依据见 [write-api-review.md](write-api-review.md)，payload、部署限制和恢复步骤见 [changes.md](changes.md)。
原服务及其配置应继续独立保留。不要为验证新代码重用原 `.env`、真实业务表或运行端口。
