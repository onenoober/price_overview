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
| 多模态模型配置 | 可选，用于识别 PDF 页面图像并辅助字段抽取。 |

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
| `extract_method` | `text_layer`、`vision_model`、`ai`、`manual`。 |

## 主要规则

| 规则 | 要求 |
|---|---|
| 先结构化再归一 | 原文抽取和标准编码归一分开保存。 |
| 低置信度不丢弃 | 低置信度字段进入结果并标记风险。 |
| 多候选保留 | 同一字段有多个候选时保留候选列表。 |
| 原文必须保留 | 归一失败也要保留原文。 |
| AI 可辅助 | AI 输出必须带输入依据和置信度。 |
| 图像解析不编造 | 多模态模型只能输出图纸图像中可见的信息；不可见字段必须返回空值和低置信度。 |

## 风险生成

| 条件 | 风险 |
|---|---|
| 关键字段置信度低于阈值 | `LOW_CONFIDENCE_FIELD` |
| 出现 H7、E8、G6、±0.01、Ra0.8 | `HIGH_PRECISION_REQUIREMENT` |
| PDF 无法读取 | 解析错误，允许转人工。 |

PDF 解析模块只负责抽取 `material_raw`、`surface_treatment_raw` 等原文及证据；`UNKNOWN_MATERIAL` 和 `UNKNOWN_SURFACE_TREATMENT` 在后续字典归一或 `part_feature` 融合阶段生成，但必须引用本模块提供的字段证据。

## 解析策略

| 阶段 | 说明 |
|---|---|
| Text layer 快路径 | 优先使用 PyMuPDF 读取 PDF 文本层和标题栏文本块，成本低且证据位置明确。 |
| 多模态图像解析 | 默认对扫描件或无文本层 PDF 启用；也可配置为对低置信度关键字段启用。解析时将 PDF 页面渲染成图片，交给已配置的多模态模型抽取结构化字段。 |
| 多模态输出校验 | 模型返回必须通过 JSON schema 校验；缺字段、类型错误或额外字段视为解析失败，不进入结构化结果。 |
| 结果融合 | 同一字段同时有 text layer 和图像候选时，保留候选、证据、置信度；低置信度字段进入人工确认。 |
| Tesseract/Pillow 识别路径 | 不再使用，扫描件由多模态图像解析承担。 |

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

## 当前配置

| 配置 | 说明 |
|---|---|
| `PRICE_PDF_VISION_MODE` | `off`、`fallback`、`low_confidence`、`always`；默认 `fallback`。 |
| `PRICE_PDF_VISION_MODEL` | 多模态模型名；未设置时复用 `PRICE_AI_MODEL`、`OPENAI_MODEL` 或 `LLM_MODEL`。 |
| `PRICE_PDF_VISION_BASE_URL` | 多模态接口地址；未设置时复用 `PRICE_AI_BASE_URL`、`OPENAI_BASE_URL` 或 `LLM_BASE_URL`。 |
| `PRICE_PDF_VISION_API_MODE` | `responses` 或 `chat_completions`；兼容接口通常使用 `chat_completions`。 |
| `PRICE_PDF_VISION_API_KEY` | 多模态 API key；未设置时复用现有 AI key 环境变量。 |
| `PRICE_PDF_VISION_DPI` | PDF 页面渲染 DPI，默认 120。 |
| `PRICE_PDF_VISION_MAX_PAGES` | 单次送入模型的最大页数，默认 2。 |
| `PRICE_PDF_VISION_TIMEOUT_SECONDS` | 多模态解析超时，默认 90 秒。 |

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

