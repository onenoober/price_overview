# GitHub 协同规范

## 分支

| 分支 | 用途 | 合并规则 |
|---|---|---|
| `main` | 稳定可演示版本。 | 只从 `develop` 合并。 |
| `develop` | 日常集成分支。 | 通过 PR 合并。 |
| `feature/*` | 功能开发。 | 合并到 `develop`。 |
| `fix/*` | 缺陷修复。 | 合并到 `develop`。 |
| `docs/*` | 文档调整。 | 合并到 `develop`。 |

分支命名：

```text
feature/pricing-rule-engine
feature/pdf-field-extraction
feature/review-page-editing
fix/missing-price-risk
docs/update-data-contracts
```

## Issue 规则

每个开发任务必须有 Issue。

Issue 必须包含：

```text
目标：
范围：
输入：
输出：
相关文档：
验收标准：
不包含：
```

Issue 拆分要求：

| 要求 | 说明 |
|---|---|
| 单一目标 | 一个 Issue 只解决一个明确问题。 |
| 可验收 | 必须能判断完成或未完成。 |
| 可测试 | 必须有测试或手动验证方式。 |
| 不跨边界 | 同时涉及 A/B 的任务应拆成两个 Issue 和一个联调 Issue。 |

## PR 规则

PR 必须从功能分支提交到 `develop`。

PR 描述必须包含：

```text
变更内容：
影响范围：
相关 Issue：
相关文档：
测试方式：
测试结果：
是否修改数据契约：
是否修改 API：
是否修改报价公式：
是否需要联调：
```

合并前检查：

| 检查项 | 要求 |
|---|---|
| CI | 必须通过。 |
| Review | 至少另一名开发者 review。 |
| 文档 | 涉及契约、规则、接口必须更新文档。 |
| 测试 | 新增逻辑必须有测试或样本验证。 |
| 冲突 | 合并前解决冲突。 |

## Review 重点

| 类型 | Review 重点 |
|---|---|
| 数据结构 | 字段是否符合契约，是否破坏兼容。 |
| API | 入参出参是否符合文档，错误是否结构化。 |
| 工序规则 | 触发条件是否清晰，是否有误判风险。 |
| 工程量 | 单位、公式、依据是否完整。 |
| 价格规则 | 价格来源、版本、公式是否可追溯。 |
| 页面 | 状态是否完整，是否展示风险和修改原因。 |
| AI | 是否保留证据、置信度，是否越权决定价格。 |

## 合并节奏

建议：

| 节奏 | 要求 |
|---|---|
| 每日同步 | 每天从 `develop` 拉取最新代码。 |
| 小 PR | PR 尽量控制在一个模块或一个 Issue。 |
| 高频合并 | 功能达到可测试状态后尽快合并。 |
| 联调分支 | 如需多人联调，可临时建立 `integration/*`。 |
| 稳定发布 | 达到阶段目标后从 `develop` 合并到 `main` 并打 tag。 |

## Tag 规则

版本 tag：

| tag | 含义 |
|---|---|
| `v0.1` | 文件解析、字段抽取、STEP 基础几何解析。 |
| `v0.2` | 工序识别、工程量计算、工序解释。 |
| `v0.3` | 价格规则、初始报价、报价明细。 |
| `v0.4` | 最终核对、人工修改、修改留痕。 |
| `v1.0` | 第一版上线验收版本。 |

## 文档变更规则

以下情况必须和代码同 PR 更新文档：

| 代码变更 | 文档 |
|---|---|
| 新增字段 | `docs/04_data_contracts.md` 和 Schema。 |
| 修改接口 | `docs/05_api_contracts.md`。 |
| 修改模块边界 | `docs/01_architecture.md` 和模块文档。 |
| 修改工序规则 | `docs/modules/process_recognition.md`。 |
| 修改工程量公式 | `docs/modules/quantity_calculation.md`。 |
| 修改报价公式 | `docs/modules/quote_calculation.md`。 |
| 修改验收口径 | `docs/06_testing_and_acceptance.md`。 |

