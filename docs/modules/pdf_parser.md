# PDF 图纸解析模块

## 模块目标

从 PDF 图纸中抽取报价所需字段，并保存原文证据、页码或位置、置信度。PDF 解析模块输出结构化 `pdf_extract_result`，不直接生成报价。

## 主责

开发者 B 主责。

## 输入

| 输入 | 说明 |
|---|---|
| `task_id` | 报价任务 ID。 |
| `file_id` | PDF 文件 ID。 |
| PDF 文件内容 | 图纸文件。 |
| 字典 | 材料、表面处理、热处理、风险标签。 |
| AI 配置 | 可选，用于辅助字段抽取和归一。 |

## 输出

| 输出 | 说明 |
|---|---|
| `pdf_extract_result` | 字段抽取结果。 |
| 字段证据 | 原文、页码、位置、置信度。 |
| 字段风险 | 低置信度、未知材料、未知表面处理等。 |

## 必抽字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `drawing_no` | string | 图号。 |
| `part_name` | string | 零件名称。 |
| `revision` | string | 版本。 |
| `material_raw` | string | 材料原文。 |
| `weight_raw` | string | 重量原文。 |
| `weight_value` | number | 重量数值。 |
| `weight_unit` | string | 重量单位。 |
| `scale` | string | 比例。 |
| `heat_treatment_raw` | string | 热处理要求原文。 |
| `surface_treatment_raw` | string | 表面处理要求原文。 |
| `tolerance_texts` | array | 公差文本。 |
| `roughness_texts` | array | 粗糙度文本。 |
| `technical_requirements` | array | 技术要求。 |

## 字段证据格式

每个抽取字段必须尽量保存：

| 字段 | 说明 |
|---|---|
| `raw_text` | PDF 原文。 |
| `page` | 页码。 |
| `location` | 标题栏、技术要求区、标注区等。 |
| `confidence` | 0-1。 |
| `extract_method` | `ocr`、`text_layer`、`ai`、`manual`。 |

## 主要规则

| 规则 | 要求 |
|---|---|
| 先结构化再归一 | 原文抽取和标准编码归一分开保存。 |
| 低置信度不丢弃 | 低置信度字段进入结果并标记风险。 |
| 多候选保留 | 同一字段有多个候选时保留候选列表。 |
| 原文必须保留 | 归一失败也要保留原文。 |
| AI 可辅助 | AI 输出必须带输入依据和置信度。 |

## 风险生成

| 条件 | 风险 |
|---|---|
| 关键字段置信度低于阈值 | `LOW_CONFIDENCE_FIELD` |
| 材料无法归一 | `UNKNOWN_MATERIAL` |
| 表面处理无法归一 | `UNKNOWN_SURFACE_TREATMENT` |
| 出现 H7、E8、G6、±0.01、Ra0.8 | `HIGH_PRECISION_REQUIREMENT` |
| PDF 无法读取 | 解析错误，允许转人工。 |

## 不做什么

- 不计算 STEP 几何。
- 不直接生成 `process_route`。
- 不计算报价。
- 不把 AI 结果直接当最终事实。
- 不在无证据时补全材料或重量。

## 关联数据

| 数据 | 说明 |
|---|---|
| `part_file` | PDF 文件来源。 |
| `pdf_extract_result` | 本模块输出。 |
| `part_feature` | 后续融合模块消费。 |

## 验收标准

- PDF 关键字段抽取准确率 >= 90%。
- 每个关键字段有证据和置信度。
- 低置信度字段能进入待确认。
- 未知材料和高精度要求能生成风险。

## AI Coding 注意事项

- 不要把抽取结果只保存为一段自然语言。
- 不要在解析失败时中断整个报价任务。
- 不要省略字段来源。
- 不要用 AI 编造 PDF 中不存在的信息。

