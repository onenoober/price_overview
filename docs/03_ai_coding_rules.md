# AI Coding 约束

## 必读顺序

每次让 AI 开发前，必须让 AI 先阅读与任务相关的文档。

通用必读：

1. `docs/00_project_overview.md`
2. `docs/01_architecture.md`
3. `docs/03_ai_coding_rules.md`

按任务追加：

| 任务类型 | 必读文档 |
|---|---|
| 数据结构 | `docs/04_data_contracts.md`、`docs/contracts/*.schema.json` |
| API | `docs/05_api_contracts.md` |
| GitHub 协作 | `docs/07_github_collaboration.md` |
| 文件上传 | `docs/modules/file_management.md` |
| PDF 解析 | `docs/modules/pdf_parser.md` |
| STEP 解析 | `docs/modules/step_parser.md` |
| 特征融合 | `docs/modules/part_feature_fusion.md` |
| 工序识别 | `docs/modules/process_recognition.md` |
| 工程量计算 | `docs/modules/quantity_calculation.md` |
| 价格规则 | `docs/modules/price_rules.md` |
| 报价计算 | `docs/modules/quote_calculation.md` |
| 核对导出 | `docs/modules/review_and_export.md` |
| AI 辅助 | `docs/modules/ai_assistance.md` |
| 历史样本 | `docs/modules/history_analysis.md` |
| 系统管理 | `docs/modules/system_management.md` |
| A 任务 | `docs/tasks/developer_a_pricing_core.md` |
| B 任务 | `docs/tasks/developer_b_parser_ui.md` |

## AI 开发提示模板

开发新任务时，推荐使用：

```text
请先阅读以下文档：
- docs/00_project_overview.md
- docs/01_architecture.md
- docs/03_ai_coding_rules.md
- docs/modules/{module}.md
- docs/tasks/{task}.md

只实现 {具体 Issue}。
不要修改无关模块。
如果需要变更数据契约、API 契约、报价公式或工序规则，先说明原因并更新对应文档。
完成后运行相关测试，并说明验证结果。
```

## 禁止行为

AI 不得执行以下行为：

| 禁止行为 | 原因 |
|---|---|
| 未读文档直接开发 | 容易偏离模块边界。 |
| 擅自新增核心数据字段 | 会破坏 A/B 联调契约。 |
| 擅自删除核心字段 | 会破坏已有样本和接口。 |
| 擅自修改报价公式 | 影响价格可信度和验收。 |
| 擅自修改工序工程量口径 | 影响报价明细一致性。 |
| 用 AI 输出直接生成最终价 | 违反系统定位。 |
| 覆盖系统初始报价 | 必须保留初始报价和人工修改。 |
| 跳过人工确认 | 存在必确认风险时不得直接确认。 |
| 大范围重构无关文件 | 增加冲突和联调风险。 |
| 混合多个 Issue 到一个 PR | 不利于 review 和回滚。 |

## 数据契约规则

AI 修改数据结构时必须遵守：

| 规则 | 要求 |
|---|---|
| 先文档后代码 | 先更新 `docs/04_data_contracts.md` 和对应 Schema。 |
| 字段可追溯 | 关键字段必须保留 `source`、`confidence` 或 `evidence`。 |
| 状态枚举固定 | 任务状态、风险等级、报价状态不得使用自由文本。 |
| 兼容 mock 数据 | 修改后必须更新 mock 或测试样本。 |
| 不删除历史字段 | 除非明确迁移方案，否则不得删除已使用字段。 |

## 报价规则

AI 不得把价格计算写成不可解释的黑盒。

每个报价项必须能追溯：

| 信息 | 要求 |
|---|---|
| 工序 | 来自 `process_route`。 |
| 工程量 | 来自 `engineering_quantity`。 |
| 单价 | 来自 `price_rule`。 |
| 价格来源 | 档案导入、人工维护、供应商报价或历史参考。 |
| 公式 | 保存计算表达式或规则编码。 |
| 风险加价 | 保存风险编码和加价依据。 |

## AI 结果处理规则

| AI 输出 | 必须处理 |
|---|---|
| 字段抽取 | 保存原文证据、页码或位置、置信度。 |
| 材料归一 | 保存原文、标准编码、匹配方式、置信度。 |
| 表面处理归一 | 保存原文、标准编码、匹配方式、置信度。 |
| 工序解释 | 只能作为说明，不得改变规则结果。 |
| 异常提示 | 必须映射到结构化风险项。 |

## 测试要求

AI 完成代码后必须执行或补充：

| 类型 | 要求 |
|---|---|
| 单元测试 | 规则、计算、归一、状态流转必须覆盖。 |
| 契约测试 | 核心输出必须符合 JSON Schema。 |
| 集成测试 | 至少验证主链路输入输出。 |
| 样本测试 | 使用黄金样本或边界样本验证。 |
| 页面测试 | 页面必须覆盖加载、成功、警告、错误状态。 |

## PR 输出要求

AI 提交或说明 PR 时必须包含：

```text
变更内容：
影响模块：
相关 Issue：
相关文档：
测试结果：
是否变更数据契约：
是否变更 API：
是否影响报价公式：
是否需要联调：
```

## 冲突处理

当 AI 发现以下情况时必须停止继续扩大改动：

| 情况 | 处理 |
|---|---|
| 文档与代码不一致 | 先说明差异，等待确认或单独修正文档。 |
| 数据契约缺字段 | 先提出契约变更。 |
| 需求跨越 A/B 边界 | 拆成两个 Issue。 |
| 样本无法判断 | 标记为待确认，不写死规则。 |
| 价格口径不清楚 | 不猜测价格，输出价格缺失风险。 |
