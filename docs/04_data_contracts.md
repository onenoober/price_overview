# 数据契约

## 契约原则

核心数据契约用于 A/B 并行开发和联调。所有模块必须以这些结构作为输入输出边界。

约束：

| 约束 | 要求 |
|---|---|
| 字段稳定 | 已进入契约的字段不得随意改名或删除。 |
| 版本明确 | 每个核心契约必须带 `schema_version`。 |
| 来源明确 | 关键字段必须可追溯来源。 |
| 置信度明确 | AI 或解析得到的字段必须带置信度。 |
| 风险结构化 | 风险不得只写成普通字符串。 |
| 金额精度 | 金额统一使用十进制数值，货币默认为 CNY。 |
| 单位明确 | 重量、长度、面积、体积、工时必须带单位。 |

## 公共字段

所有核心结果建议包含：

| 字段 | 类型 | 要求 |
|---|---|---|
| `schema_version` | string | 当前契约版本，第一版为 `1.0`。 |
| `task_id` | string | 报价任务 ID。 |
| `created_at` | string | ISO 8601 时间。 |
| `updated_at` | string | ISO 8601 时间。 |

## 来源对象 `source_ref`

用于说明字段来源。

| 字段 | 类型 | 说明 |
|---|---|---|
| `source_type` | enum | `pdf`、`step`、`manual`、`rule`、`ai`、`price_rule`、`system`。 |
| `file_id` | string | 来源文件 ID，可为空。 |
| `page` | number | PDF 页码，可为空。 |
| `location` | string | 原始位置描述，可为空。 |
| `raw_text` | string | 原文证据，可为空。 |
| `rule_code` | string | 规则编码，可为空。 |

## 风险对象 `risk_item`

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | string | 稳定风险编码。 |
| `level` | enum | `info`、`warning`、`blocking`。 |
| `message` | string | 中文提示。 |
| `source` | string | 来源模块。 |
| `requires_review` | boolean | 是否必须人工确认。 |
| `evidence` | array | 证据列表。 |

风险编码必须使用稳定英文编码，例如：

| 编码 | 含义 |
|---|---|
| `MISSING_PDF` | 缺 PDF。 |
| `MISSING_STEP` | 缺 STEP。 |
| `WEIGHT_MISMATCH` | PDF 重量与 STEP 理论重量偏差超过阈值。 |
| `UNKNOWN_MATERIAL` | 材料无法归一或缺价格。 |
| `UNKNOWN_SURFACE_TREATMENT` | 表面处理无法归一。 |
| `LOW_CONFIDENCE_FIELD` | 关键字段低置信度。 |
| `HIGH_PRECISION_REQUIREMENT` | 高精度要求。 |
| `HIGH_RISK_GEOMETRY` | 高风险几何。 |
| `MISSING_PRICE` | 价格缺失。 |
| `PRICE_OUTLIER` | 价格偏离历史区间。 |

## `part_feature`

用途：PDF 字段、STEP 几何、字典归一后的统一零件特征。

Schema 文件：`docs/contracts/part_feature.schema.json`

必要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `part` | object | 零件基础信息。 |
| `material` | object | 材料原文、标准编码、密度、置信度。 |
| `geometry` | object | 包络尺寸、体积、面积、重量、零件类型。 |
| `features` | object | 孔、槽、精度、复杂度等结构化特征。 |
| `manufacturing_requirements` | object | 热处理、表面处理、去毛刺、检验等要求。 |
| `risks` | array | 风险项。 |
| `evidence` | array | 关键证据。 |

开发要求：

- PDF 和 STEP 都存在时必须融合。
- 缺 PDF 或缺 STEP 时仍允许生成 `part_feature`，但必须写入风险。
- 材料未知时不得编造密度和单价。
- STEP 理论重量和 PDF 标注重量偏差超过 15% 必须生成 `WEIGHT_MISMATCH`。

## `process_route`

用途：工序识别结果。

Schema 文件：`docs/contracts/process_route.schema.json`

必要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `route_id` | string | 工序路线 ID。 |
| `family` | string | 新版路线引擎判定的制造族，例如 `MACHINING`、`SHEET_METAL`。 |
| `business_category` | string/null | PDF/业务小类路由结果，例如 `方件类`；无法识别时可为空。 |
| `operations` | array | 工序列表。 |
| `risks` | array | 工序相关风险。 |
| `requires_review` | boolean | 是否需要人工复核。 |

工序对象必要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `operation_code` | string | 工序编码。字典外工序统一使用 `unmapped_operation`。 |
| `operation_name` | string | 工序名称。`unmapped_operation` 必须保留原始识别名称，例如 `未登记工序：喷砂`。 |
| `sequence` | number | 工序顺序。 |
| `trigger_reasons` | array | 触发原因。 |
| `confidence` | number | 0-1。 |
| `requires_review` | boolean | 是否需要人工确认。 |
| `explanation` | string | 可读解释。 |

开发要求：

- 工序排序必须稳定。
- 每个自动生成工序必须有触发原因。
- 低置信度工序必须标记待确认。
- `unmapped_operation` 不得自动计价，必须由人工确认后映射、新增字典工序、保留人工报价或删除。
- 工序解释不得反向改变工序结果。

## `quantity_result`

用途：各工序工程量结果。

Schema 文件：`docs/contracts/quantity_result.schema.json`

必要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `items` | array | 工程量明细。 |
| `risks` | array | 工程量相关风险。 |

工程量项必要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `operation_code` | string | 对应工序。 |
| `quantity_type` | string | 工程量类型。 |
| `value` | number | 工程量数值。 |
| `unit` | string | 单位。 |
| `formula` | string | 计算公式。 |
| `basis` | array | 计算依据。 |
| `requires_review` | boolean | 是否需要人工确认。 |

开发要求：

- 数量不能只有最终数值，必须保存公式和依据。
- 无法计算时不得填 0 伪装成功，应生成风险。
- 价格计算只能消费结构化工程量，不能重新从文本解析。

## `quote_result`

用途：初始报价、报价明细、风险、最终确认状态。

Schema 文件：`docs/contracts/quote_result.schema.json`

必要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `quote_id` | string | 报价结果 ID。 |
| `status` | enum | `priced`、`pending_review`、`confirmed`、`voided`。 |
| `currency` | string | 默认 `CNY`。 |
| `price_version` | string | 价格版本。 |
| `items` | array | 报价明细。 |
| `summary` | object | 汇总。 |
| `risks` | array | 风险。 |
| `manual_overrides` | array | 人工修改记录。 |

报价项必要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `item_type` | enum | `material`、`process`、`surface_treatment`、`management_fee`、`tax`、`risk_surcharge`、`other`。 |
| `operation_code` | string | 相关工序，可为空。 |
| `quantity` | number | 工程量。 |
| `unit` | string | 单位。 |
| `unit_price` | number | 单价。 |
| `amount` | number | 金额。 |
| `price_source` | object | 价格来源。 |
| `formula` | string | 公式。 |
| `explanation` | string | 说明。 |

开发要求：

- 人工修改不得覆盖系统初始金额。
- 存在必确认风险时 `status` 必须为 `pending_review`。
- 最终确认必须保存确认人、确认时间和修改原因。

## 数据对象清单

| 数据对象 | 用途 | 主责 |
|---|---|---|
| `quote_task` | 报价任务主表。 | A |
| `part_file` | 文件记录。 | B |
| `pdf_extract_result` | PDF 字段抽取结果。 | B |
| `step_feature_result` | STEP 几何解析结果。 | B |
| `part_feature` | 融合后零件特征。 | A/B |
| `process_route` | 工序路线。 | A |
| `engineering_quantity` | 工程量。 | A |
| `price_rule` | 价格规则。 | A |
| `price_source_record` | 价格来源。 | A |
| `quote_item` | 报价明细。 | A |
| `quote_summary` | 报价汇总。 | A |
| `human_override` | 人工修改记录。 | A/B |
| `quote_history_sample` | 历史报价样本。 | A |

