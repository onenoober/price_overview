# STEP 几何解析模块

## 模块目标

从 STEP 模型中提取基础几何、重量估算、孔特征、复杂度和零件类型候选，输出 `step_feature_result`。本模块不负责工序识别和报价。

当前主流程实现：`backend.app.parser_service.RealStepParser` 已接入
`standalone_step_parser.step_parser.parse_step_file`。默认 `PRICE_PARSER_MODE=auto`
下，STEP 解析失败会记录解析失败风险，不再回退或生成替代 STEP 几何。

## 主责

开发者 B 主责。

## 输入

| 输入 | 说明 |
|---|---|
| `task_id` | 报价任务 ID。 |
| `file_id` | STEP 文件 ID。 |
| STEP 文件内容 | `.step` 或 `.stp`。 |
| 材料密度 | 可选，来自材料归一结果。 |

## 输出

| 输出 | 说明 |
|---|---|
| `step_feature_result` | STEP 结构化解析结果。 |
| 几何风险 | 复杂件、高风险几何、解析失败等。 |

## 必须输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `bounding_box` | object | 长、宽、高、单位。 |
| `volume` | object | 体积、单位。 |
| `surface_area` | object | 表面积、单位。 |
| `net_weight` | object | 理论净重、单位、密度来源。 |
| `part_type_candidates` | array | 零件类型候选。 |
| `holes` | array | 孔特征候选。 |
| `complexity` | object | 面数、边数、复杂度评分等。 |
| `geometry_risks` | array | 几何风险。 |

## 孔特征

孔特征候选字段：

| 字段 | 说明 |
|---|---|
| `hole_type` | `through`、`blind`、`counterbore`、`countersink`、`thread_candidate`、`precision_candidate`。 |
| `diameter` | 直径。 |
| `depth` | 深度，可为空。 |
| `count` | 数量。 |
| `confidence` | 0-1。 |
| `evidence` | 几何依据。 |

## 零件类型候选

| 类型 | 判断依据 |
|---|---|
| `thin_plate` | 厚度明显小于长宽。 |
| `plate` | 板状特征明显。 |
| `block` | 长宽高相对接近。 |
| `shaft` | 轴类特征明显。 |
| `complex` | 曲面、复杂外形、装配或无法稳定解析。 |

第一版不自动核价的类型：

- `shaft`
- `complex`
- 焊接件
- 装配件

这些类型应生成转人工风险。

## 复杂度特征

| 字段 | 说明 |
|---|---|
| `face_count` | 面数量。 |
| `edge_count` | 边数量。 |
| `small_radius_count` | 小 R 候选数量。 |
| `slot_count` | 槽候选数量。 |
| `thin_wall_candidate` | 是否薄壁候选。 |
| `complexity_score` | 0-100。 |

## 风险生成

| 条件 | 风险 |
|---|---|
| STEP 缺失 | `MISSING_STEP` |
| STEP 无法解析 | 解析失败风险。 |
| 复杂件或轴类件 | `HIGH_RISK_GEOMETRY` 或转人工风险。 |
| 小 R、窄槽、深孔、薄壁、长悬臂 | `HIGH_RISK_GEOMETRY` |

## 不做什么

- 不抽取 PDF 字段。
- 不决定工序路线。
- 不直接生成工程量。
- 不直接生成报价。
- 不在缺材料密度时编造重量。

## 验收标准

- STEP 基础几何解析成功率 >= 95%。
- 成功样本必须输出尺寸、体积、表面积。
- 有密度时可计算理论净重，并说明密度来源。
- 复杂件或不支持件必须标记待人工处理。

## AI Coding 注意事项

- 不要把几何特征写成不可解析的说明文本。
- 不要把 `complexity_score` 当报价依据的唯一来源。
- 不要用 STEP 文件名推断材料。
- 不要忽略解析失败的错误信息。

