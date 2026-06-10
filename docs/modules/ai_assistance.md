# AI 辅助模块

## 模块目标

AI 辅助模块用于图纸字段抽取、文本归一、工序解释、异常提示和后续修改复盘。AI 只提供辅助结果，不拥有最终定价权、规则变更权或自动放行权。

## 主责

开发者 B 主责 AI 接入和展示，开发者 A 提供规则命中原因、风险编码和报价依据。

## 允许的 AI 能力

| 能力 | 输入 | 输出 |
|---|---|---|
| PDF 字段抽取辅助 | PDF 文本、页面图像、多模态解析候选、页面区域 | 字段候选、原文证据、置信度。 |
| 文本归一 | 材料原文、表面处理原文、技术要求 | 标准编码候选、匹配理由、置信度。 |
| 工序原因解释 | 规则命中结果、触发原因 | 给报价员看的解释文本。 |
| 异常提示说明 | 风险编码、证据、上下文 | 复核建议。 |
| 修改复盘辅助 | 人工修改记录、最终结果 | 高频漏项、改价原因归类建议。 |

## 禁止的 AI 能力

| 禁止项 | 说明 |
|---|---|
| 自动决定最终报价 | 最终报价必须人工确认。 |
| 自动覆盖价格库 | 价格规则必须人工维护和审核。 |
| 自动新增正式工序规则 | AI 可提出建议，不可直接生效。 |
| 无证据生成关键字段 | 材料、重量、热处理、表面处理必须有来源。 |
| 跳过人工确认 | 有必确认风险时不得直接确认。 |

## AI 输出要求

AI 输出必须结构化保存：

| 字段 | 要求 |
|---|---|
| `task_id` | 所属报价任务。 |
| `input_type` | `pdf_text`、`field_text`、`rule_result`、`risk_item`、`override_history`。 |
| `output_type` | `field_candidate`、`normalization`、`explanation`、`risk_suggestion`、`analysis`。 |
| `content` | AI 输出内容。 |
| `confidence` | 0-1。 |
| `evidence` | 输入依据。 |
| `model_name` | 模型名称。 |
| `prompt_version` | 提示词版本。 |
| `created_at` | 生成时间。 |

## 字段抽取规则

| 场景 | 要求 |
|---|---|
| 有多个候选 | 保留候选列表，不直接覆盖。 |
| 低置信度 | 标记 `LOW_CONFIDENCE_FIELD`。 |
| 原文冲突 | 保留冲突证据，进入人工确认。 |
| 无原文证据 | 不得作为关键字段输出。 |

## 工序解释规则

AI 解释只能基于已经生成的 `process_route`。

允许：

- 将触发原因转成自然语言。
- 说明为什么需要某道工序。
- 说明为什么需要人工复核。

禁止：

- 新增规则未命中的工序。
- 删除规则已命中的工序。
- 修改工序顺序。
- 修改置信度。

## 异常提示规则

AI 可把结构化风险转成用户可读说明，但不得改变风险等级。

输入示例：

```text
风险编码：WEIGHT_MISMATCH
证据：PDF 重量 1.2kg，STEP 理论重量 0.8kg，偏差 50%
```

输出要求：

```text
说明重量偏差原因可能来自材料、比例、模型版本或图纸标注，需要人工确认。
```

## 降级规则

| AI 状态 | 系统处理 |
|---|---|
| AI 调用失败 | 规则链路继续运行，标记 AI 结果不可用。 |
| AI 超时 | 返回基础规则结果。 |
| AI 输出格式错误 | 丢弃本次 AI 输出，记录错误。 |
| AI 低置信度 | 输出候选但待确认。 |

## 不做什么

- 不把 AI 作为报价计算来源。
- 不把 AI 作为价格来源。
- 不让 AI 修改审核通过的规则。
- 不让 AI 输出无证据关键字段。

## 验收标准

- AI 输出可追溯输入和提示词版本。
- AI 失败不阻塞主流程。
- AI 不改变规则计算结果。
- AI 提示能映射到结构化风险或解释。

## AI Coding 注意事项

- 不要把提示词散落在多个业务函数中。
- 不要让前端直接信任 AI 输出并写入最终字段。
- 不要忽略模型调用失败。
- 不要把 AI 解释当作规则判断依据。

## 当前实现

后端通过 `AiAssistanceService` 接口接入 AI，默认使用可降级实现：

| 配置 | 说明 |
|---|---|
| `PRICE_AI_PROVIDER=auto` | 默认值。有 API key 时调用真实 AI，否则保存 AI 不可用记录。 |
| `PRICE_AI_PROVIDER=openai` | 使用 OpenAI 或兼容接口；调用失败时保存 AI 不可用记录，不生成替代分析。 |
| `PRICE_AI_API_MODE` / `LLM_API_MODE` | `responses` 或 `chat_completions`；DashScope 兼容模式使用 `chat_completions`。 |
| `PRICE_AI_MODEL` / `OPENAI_MODEL` / `LLM_MODEL` | 模型名称，默认 `gpt-5.5`。 |
| `PRICE_AI_BASE_URL` / `OPENAI_BASE_URL` / `LLM_BASE_URL` | API 地址，默认 `https://api.openai.com/v1`。 |
| `OPENAI_API_KEY` / `PRICE_AI_API_KEY` / `LLM_API_KEY` / `DASHSCOPE_API_KEY` | API key。 |
| `PRICE_AI_TIMEOUT_SECONDS` | 单次 AI 调用超时时间，默认 20 秒。 |

本地开发可将这些变量写入 `backend/.env.local`。该文件被 `.gitignore` 忽略，已有 shell 环境变量优先级更高。

实现边界：

- 解析阶段保存材料归一、表面处理归一和风险解释。
- 核价阶段保存工序解释，但不改写 `process_route`、工序顺序或置信度。
- 任务详情接口返回 `ai_outputs`，核对页面的“AI 辅助”页只读展示这些记录。
- 真实调用失败或缺少 API key 时，主流程继续运行，并保存 `ai-unavailable` 状态记录。
- 未配置真实 AI 时只保存 AI 不可用记录，不生成替代分析。

