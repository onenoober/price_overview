# 开发者文档分配表

## 使用方式

每个开发者只需要长期关注自己的任务文档、相关模块文档、共同契约文档。其他文档在跨模块联调或改接口时再读。

## 共同必读文档

A 和 B 都必须阅读：

| 文档 | 用途 |
|---|---|
| `docs/00_project_overview.md` | 项目范围、第一版做什么和不做什么。 |
| `docs/01_architecture.md` | 模块边界、数据流、状态流转。 |
| `docs/03_ai_coding_rules.md` | AI coding 禁止事项和开发约束。 |
| `docs/04_data_contracts.md` | 核心数据结构。 |
| `docs/05_api_contracts.md` | API 入参出参。 |

## A：核价核心开发者

A 必读：

| 顺序 | 文档 | 用途 |
|---:|---|---|
| 1 | `docs/tasks/developer_a_pricing_core.md` | A 的任务总表。 |
| 2 | `docs/modules/process_recognition.md` | 工序识别规则。 |
| 3 | `docs/modules/quantity_calculation.md` | 工程量计算口径。 |
| 4 | `docs/modules/price_rules.md` | 价格规则和价格版本。 |
| 5 | `docs/modules/quote_calculation.md` | 初始报价和最终确认报价。 |
| 6 | `docs/modules/history_analysis.md` | 历史样本和修改分析。 |
| 7 | `docs/modules/system_management.md` | 字典、参数、权限、日志。 |

A 需要重点维护：

| 文件 | 说明 |
|---|---|
| `docs/contracts/process_route.schema.json` | 工序识别输出契约。 |
| `docs/contracts/quantity_result.schema.json` | 工程量输出契约。 |
| `docs/contracts/quote_result.schema.json` | 报价结果输出契约。 |

A 的开发边界：

- 可以消费 B 输出的 `part_feature`。
- 不直接解析 PDF 原文。
- 不直接解析 STEP 文件。
- 不开发复杂页面样式。
- 不让 AI 决定最终报价。

## B：解析与页面开发者

B 必读：

| 顺序 | 文档 | 用途 |
|---:|---|---|
| 1 | `docs/tasks/developer_b_parser_ui.md` | B 的任务总表。 |
| 2 | `docs/modules/file_management.md` | 文件上传、绑定、版本。 |
| 3 | `docs/modules/pdf_parser.md` | PDF 字段抽取。 |
| 4 | `docs/modules/step_parser.md` | STEP 几何解析适配。 |
| 5 | `docs/modules/part_feature_fusion.md` | PDF/STEP 融合成 `part_feature`。 |
| 6 | `docs/modules/ai_assistance.md` | AI 辅助边界。 |
| 7 | `docs/modules/review_and_export.md` | 核对页面和导出。 |

B 需要重点维护：

| 文件 | 说明 |
|---|---|
| `docs/contracts/part_feature.schema.json` | 零件特征输出契约。 |
| `docs/05_api_contracts.md` | 涉及页面调用的接口契约。 |

B 的开发边界：

- 可以生成 `part_feature`。
- 可以展示 A 输出的报价结果。
- 不在前端重写报价公式。
- 不直接修改价格规则。
- 不让 AI 覆盖价格库或最终报价。

## A/B 共同负责

| 文档 | 用途 |
|---|---|
| `docs/tasks/integration_checklist.md` | 联调检查。 |
| `docs/06_testing_and_acceptance.md` | 验收标准。 |
| `docs/07_github_collaboration.md` | GitHub 简单协作规则。 |

## 推荐开发顺序

### 第一步：共同准备

1. 确认本地能运行项目。
2. 确认 A/B 都能拉取和推送仓库。
3. 确认分支使用方式。
4. 先用 mock 数据跑通主流程。

### 第二步：A/B 并行

A 先做：

1. 数据模型。
2. 字典和价格规则。
3. 工序识别。
4. 工程量计算。
5. 报价计算。

B 先做：

1. 文件上传。
2. PDF/STEP 解析适配。
3. `part_feature` 输出。
4. 核对页面。
5. 导出。

### 第三步：联调

共同按 [integration_checklist.md](integration_checklist.md) 检查：

1. B 输出 `part_feature`。
2. A 消费 `part_feature`。
3. A 输出 `process_route`、`quantity_result`、`quote_result`。
4. B 展示报价。
5. 人工修改保存。
6. 最终确认和导出。

## AI Coding 提示示例

A 使用：

```text
请先阅读 docs/00_project_overview.md、docs/03_ai_coding_rules.md、
docs/tasks/developer_a_pricing_core.md、docs/modules/quote_calculation.md。
只实现报价计算相关功能，不修改 PDF/STEP 解析和前端页面。
```

B 使用：

```text
请先阅读 docs/00_project_overview.md、docs/03_ai_coding_rules.md、
docs/tasks/developer_b_parser_ui.md、docs/modules/pdf_parser.md。
只实现 PDF 字段抽取相关功能，不修改报价计算和价格规则。
```

