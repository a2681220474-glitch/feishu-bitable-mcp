# 开发交接：四类资源写入（2026-11-17）

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

本地 Python 3.12 下 335 项 Mock 测试、Ruff 检查通过；不依赖飞书凭证。
完整模拟覆盖 OAuth 注册/同意/PKCE、授权码及刷新、Scope 缺失/部分授予、不同用户并发写入的 Token 隔离、MCP 预览/确认/回执链路、重启防重复、未知结果租约和资源冲突。
XLSX 测试回读修改结果，并逐个核对无关 ZIP 条目，包含图表、样式、未改公式和其他工作表。
本轮没有读取或修改真实飞书业务资源、应用配置或用户 Token，没有新增测试数据。
安装包验证及 PR CI 的最新结果以交付报告和 GitHub 检查为准。

## 尚待完成的验收

1. 使用独立测试应用/测试文件，以真实用户 OAuth 分别验证最小写 Scope、读取预检权限和实际资源 ACL；不使用业务文件。
2. 从 ChatGPT 网页端实测预览、拒绝、确认、超时后查询、撤销和重新授权，不以 Mock 冒充端到端结果。
3. 用真实测试 XLSX 验证官方 CLI 同 token 上传参数、目录/文件名行为和保存内容；当前额外配置关闭，不宣称已有可用版本历史。
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
