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

## A 侧 mock 核价核心

当前 A 侧已提供第一阶段 mock 核价链路：

```text
mock part_feature
-> process_route
-> quantity_result
-> quote_result
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

生成 mock 核价结果：

```bash
python scripts/run_mock_pricing.py --output fixtures/mock/mock_pricing_result.json
```

默认输入：

```text
fixtures/mock/part_feature_plate_skd11.json
```

输出会按以下契约校验：

```text
docs/contracts/process_route.schema.json
docs/contracts/quantity_result.schema.json
docs/contracts/quote_result.schema.json
```

价格规则当前为 A 侧结构化 mock 规则：

```text
src/price_overview/pricing_core/price_rules.py
```

支持审核状态、版本、生效期、单位匹配、优先级、起步价和缺价风险。

