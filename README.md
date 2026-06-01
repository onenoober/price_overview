# price_overview

工件核价系统开发仓库。

## 文档入口

先读：

- [docs/README.md](docs/README.md)
- [docs/tasks/developer_document_map.md](docs/tasks/developer_document_map.md)
- [docs/tasks/preparation_checklist.md](docs/tasks/preparation_checklist.md)

## 简单协作方式

- 开发者 A 负责核价核心、规则、工程量、价格、报价计算。
- 开发者 B 负责文件上传、PDF/STEP 解析、AI 辅助、核对页面、导出。
- 两人共同维护数据契约和联调清单。

建议分支：

- `dev-a`：A 日常开发分支。
- `dev-b`：B 日常开发分支。
- `main`：可运行或可演示版本。

每次合并前，至少确认：

- 没有改动对方负责模块的核心逻辑。
- 没有破坏 `docs/contracts` 中的数据契约。
- 主流程能跑通或明确说明还不能跑通的原因。

