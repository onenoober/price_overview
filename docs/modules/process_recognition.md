# 工序识别模块

## 模块目标

根据 `part_feature` 和工序规划规则生成可解释的 `process_route`。系统采用分层路线：

```text
Feature Extractor -> Process Planner(Stage) -> Operation Expander -> Quote Planner
```

`Feature Extractor` 只输出材料、几何、孔、精度、热处理、表面处理等客观事实；`Process Planner`
先生成制造阶段路线 `stage_route`；`Operation Expander` 再把阶段展开成标准细分工序
`operations`；报价引擎继续按 `operations.quote_process_code` 归并计价。AI 只能参与
Stage Planning 或解释说明，不能直接绕过字典生成自动计价工序。

阶段和详细工序必须保持一致：最终输出会为每个详细工序写入 `stage_code/stage_name`，
并把每个阶段真实展开出的工序反写到 `stage_route.actual_operation_codes`。如果阶段已规划
但没有展开出任何对应详细工序，系统必须输出 `STAGE_WITHOUT_OPERATION` 风险并标记该阶段需复核。

## 主责

开发者 A 主责。

## 输入

| 输入 | 说明 |
|---|---|
| `part_feature` | 统一零件特征。 |
| 工序字典 | 标准工序编码、名称、排序。 |
| 工序触发规则 | 材料、几何、孔、精度、表面处理等规则。 |
| 风险规则 | 低置信度、高风险、未知字段。 |

## 输出

| 输出 | 说明 |
|---|---|
| `process_route.stage_route` | 工艺阶段路线，表达工程师式制造顺序。 |
| `process_route.operations` | 阶段展开后的标准细分工序，用于工程量和报价。 |
| 工序触发原因 | 每个工序的命中依据。 |
| 工序置信度 | 0-1。 |
| 待确认标记 | 是否需要人工确认。 |

## Stage 字典

`stage_route` 是工艺路线的主骨架，不直接计价。阶段定义在
`backend/app/process_recognition.py` 的 `STAGE_DEFINITIONS` 中，必须按
`STAGE_SEQUENCE` 排序。

`planned_operation_codes` 表示该阶段可能包含的候选工序范围；`actual_operation_codes`
表示本次路线真实展开出来的详细工序，前端应优先展示 `actual_operation_codes`。

| Stage | 中文名 | 作用 |
|---|---|---|
| `material_preparation` | 来料/备料 | 确认材料牌号、规格、毛坯状态并备料。 |
| `blanking` | 下料/开料 | 规划锯切、激光、线割等开料方式。 |
| `fixture_and_datum` | 装夹/基准建立 | 规划装夹、找正、夹具、防变形支撑和基准。 |
| `rough_machining` | 主体粗加工 | 建立主要基准并去除大余量。 |
| `hole_machining` | 孔预加工 | 普通孔、侧孔、PCD 孔组和螺纹底孔。 |
| `thread_and_counterbore` | 沉孔/攻牙 | 沉孔、反面沉孔、攻牙和侧面攻牙。 |
| `profile_and_cavity` | 外形/槽/型腔加工 | 外形轮廓、槽、台阶、型腔、放电区域。 |
| `heat_and_stabilize` | 热处理/去应力 | 热处理、去应力和时效稳定。 |
| `post_heat_correction` | 热后恢复加工 | 热处理后按变形、尺寸面、孔、螺纹、氧化皮和硬度验证安排恢复加工。 |
| `finish_and_precision` | 精加工/精孔 | 精铣、精车、精密面、精孔、铰孔和镗孔。 |
| `deburr_cleaning` | 去毛刺/倒角/清洗 | 去毛刺、倒角、锐角倒钝和清洗。 |
| `pre_surface` | 表处前处理 | 镀前清洗、遮蔽螺纹/精孔/功能面。 |
| `surface_treatment` | 表面处理 | 化学镍、阳极、镀硬铬、喷塑、喷砂等。 |
| `post_surface` | 表处后处理/复检 | 回攻清牙、除氢、复铰、修磨和精孔复检。 |
| `inspection` | 专项检验/终检 | 首件、过程、螺纹、精孔、膜厚、外观和终检。 |
| `packaging` | 防护包装 | 终检后防划伤、防弯曲、防锈和防碰伤包装。 |

## 工序字典

工序识别、工程量计算、价格规则、人工修改和历史样本必须使用同一套工序编码。
第一版先使用代码版统一工序字典，后续再迁移到数据库字典。
当前代码版字典在 `backend/app/process_dictionary.py`，工序路线生成在
`backend/app/process_recognition.py`，报价核心通过该模块生成 `process_route`。

字典必须同时维护两层信息：

- `sequence`：细分工序的唯一排序号，`PROCESS_SEQUENCE` 按该字段生成。
- `quote_process_code`：细分工序归并到哪个报价主工序；例如 `blind_tapping` 参与路线排序，但报价可归并到 `tapping`。

主工序和细分工序关系如下，完整字段以 `ProcessDefinition` 为准：

| 主工序/归并工序 | 细分工序编码 | 说明 |
|---|---|---|
| `material_prepare` | `raw_material_check` | 来料确认和备料。 |
| `saw_cut` | `weld_material_cut` | 锯切下料、焊接件下料。 |
| `laser_cut` | `laser_cut_blank` | 激光开料、激光切割。 |
| `wire_cut_blank` | - | 线割开料。 |
| `cnc_milling` | `fixture_setup`, `soft_jaw_fixture`, `support_anti_deformation`, `cnc_rough_milling`, `profile_milling`, `step_milling`, `slot_milling`, `pocket_milling`, `reverse_side_machining`, `second_setup`, `side_setup`, `precision_surface_finish`, `fit_up`, `welding`, `post_weld_machining` | 装夹、夹具、防变形、粗铣、外形、台阶、槽、型腔、翻面、侧向装夹、精密面修正和焊后机加工等。 |
| `turning` | `turning_rough`, `facing`, `center_drilling`, `turning_finish`, `grooving_turning`, `chamfer_turning` | 轴类粗车、端面、中心孔、精车、车槽和车削倒角。 |
| `drilling` | `drilling_through`, `drilling_blind`, `side_hole_machining`, `pcd_hole_pattern` | 通孔、盲孔、侧孔和 PCD 孔组。 |
| `countersink` | `counterbore`, `countersink_90`, `reverse_counterbore` | 圆柱沉孔、90°沉头孔和反面沉孔。 |
| `tapping` | `tapping_through`, `blind_tapping`, `fine_thread_tapping`, `side_tapping`, `thread_chasing` | 通牙、盲孔攻牙、细牙、侧面攻牙和表处后回攻清牙。 |
| `wire_cut_profile` | - | 线切割外形、内孔、窄槽。 |
| `edm` | - | 放电加工。 |
| `heat_treatment` | `stress_relief`, `dehydrogenation_bake` | 热处理、去应力和镀后除氢。 |
| `straightening` | - | 校平、校直。 |
| `finish_grinding` | `post_chrome_polishing` | 精磨和镀硬铬后抛光/修磨。 |
| `cylindrical_grinding` | - | 圆磨。 |
| `precision_hole` | `reaming`, `boring`, `post_anodize_reaming` | 精孔、铰孔、镗孔和氧化后复铰。 |
| `deburr` | `weld_grinding` | 去毛刺、锐边倒钝、倒角和焊缝打磨。 |
| `pre_plating_cleaning` | `cleaning`, `surface_masking`, `hard_chrome_masking`, `anodize_masking`, `powder_masking`, `welding_prepare` | 清洗、表处遮蔽和焊前处理。 |
| `sand_blasting` | - | 喷砂。 |
| `chemical_nickel` | - | 化学镍、化学镀镍。 |
| `clear_anodizing` | - | 本色阳极氧化。 |
| `hard_anodizing` | - | 硬质阳极氧化。 |
| `color_anodizing` | - | 着色阳极氧化。 |
| `hard_chrome` | - | 镀硬铬。 |
| `powder_coating` | - | 喷塑。 |
| `white_powder_coating` | - | 白色喷塑。 |
| `powder_coating_texture` | - | 小桔纹喷塑。 |
| `inspection` | `weld_inspection`, `post_chrome_inspection`, `first_article_inspection`, `in_process_inspection`, `thread_inspection`, `precision_hole_inspection`, `pcd_hole_inspection`, `flatness_inspection`, `hardness_inspection`, `coating_thickness_inspection`, `surface_inspection`, `post_surface_precision_hole_check` | 焊缝、镀铬后、首件、过程、螺纹、精孔、PCD、平面度、硬度、膜厚、表面和表处后精孔检验。 |
| `protective_packaging` | - | 防划伤、防弯曲和防锈包装。 |
| `unmapped_operation` | - | 字典外工序，必须人工确认。 |
| `manual_review` | - | 解析、工艺或报价风险人工复核；只进入风险提示，不作为可见路线工序。 |

## 触发规则

工艺触发不是简单按“孔、槽、倒角、表面处理”平铺罗列，而是先建立制造决策层：

```text
图纸/技术要求硬约束
-> 零件类型和主工艺路线
-> 毛坯/下料方式
-> 装夹、找正和加工基准
-> 主体粗加工和大余量去除
-> 孔槽、螺纹、多面加工和精度特征
-> 热处理/去应力/热后恢复加工
-> 表面处理、遮蔽和表处后复检
-> 过程检验、专项检验、终检和包装
```

对应到代码时，图纸/3D 确认和路线规划只作为风险或人工复核提示，不作为正式工序输出。
制造决策层由 `raw_material_check`、`fixture_setup`、
`soft_jaw_fixture`、`support_anti_deformation`、`stress_relief`、
`in_process_inspection` 等细分工序表达；报价仍通过 `quote_process_code`
归并到主报价工序，避免把决策节点误当成新的独立大类。

| 条件 | 工序 |
|---|---|
| 任意支持零件 | 备料、下料、检验、包装。 |
| 存在材料 | 来料确认。 |
| 板件、块件、异形小件 | CNC 或线切割候选。 |
| 板件、块件、异形件、复杂件 | 装夹/找正；复杂或异形件增加软爪/专用夹具候选。 |
| 薄板、薄壁、长条、大板或高变形风险几何 | 防变形支撑、去应力候选、平面度检验。 |
| 存在普通孔 | 钻孔。 |
| 存在沉孔或沉头孔 | 沉孔。 |
| 存在螺纹孔候选 | 攻牙。 |
| 存在侧孔、端面孔或反面孔证据 | 二次装夹、侧向装夹、侧孔加工或反面加工候选。 |
| H7、E8、G6、±0.01、高精度孔 | 精孔。 |
| 存在 PCD、圆周孔组或分度孔组证据 | PCD 孔组加工和 PCD 孔组检验。 |
| 外轮廓切割、薄片件、板件 | 线切割候选。 |
| 热处理后变形、尺寸面、精孔、螺纹、氧化皮或硬度验证需求 | 热后恢复加工：校平/校直、精磨、圆磨、精孔恢复、回攻/清牙、喷砂/清洗、硬度检测候选。 |
| 高复杂度、薄壁或大去除量风险 | 粗加工后去应力/时效候选，精加工前增加过程检验。 |
| PDF 或技术要求出现热处理 | 热处理。 |
| PDF 或技术要求出现化学镍、阳极氧化、镀硬铬、喷塑、喷砂等 | 对应表面处理工序。 |
| 阳极氧化、镀硬铬、喷塑等表面处理 | 对应遮蔽候选、膜厚检验、表面外观检验；硬铬增加除氢和镀后专项检验候选。 |
| 技术要求出现去毛刺、锐角倒钝、倒角 | 去毛刺/倒角。 |
| 技术要求出现防划伤、防弯曲、防锈或包装 | 防护包装。 |
| 轴类件 | 车削；有热处理或精度要求时增加圆磨候选。 |
| 复杂件 | CNC 复杂加工估算；放电加工候选。 |
| 批量且存在复杂、多面、精孔或表处风险 | 首件检验候选。 |
| AI 基于 PDF、STEP 或融合特征识别到字典外工序 | `unmapped_operation`，保留原始工序名，必须人工确认。 |

## 冲突消解

| 冲突 | 规则 |
|---|---|
| CNC 与线切割都命中 | 按零件类型、外形复杂度、厚度和规则优先级选择主工序，可保留另一工序为待确认候选。 |
| 钻孔与精孔都命中 | 精孔不能替代钻孔，钻孔作为前置，精孔作为精加工。 |
| 热处理前后精加工 | 热处理后需要磨削或精孔时必须排序到热处理之后。 |
| 表面处理与精孔 | 表面处理影响孔径时必须生成风险。 |
| 高复杂度、轴类或特殊工艺 | 不阻断报价，输出首版估算工序并标记需复核。 |
| 字典外工序 | 输出 `unmapped_operation`，不自动计价，必须由人工映射到已有工序、新增字典工序、保留一次性人工报价或删除。 |

## 工序排序

工序识别后的输出必须排序，不能只输出无序集合。排序的唯一代码入口是
`ProcessDefinition.sequence`，`PROCESS_SEQUENCE` 会按该字段生成，
`finalize_route()` 会按 `operation_sequence_key()` 排序并重新编号。
新增细分工序时必须分配唯一 `sequence`，并补充顺序测试。

标准排序骨架：

```text
来料确认
-> 备料
-> 下料/开料
-> 装夹/找正/夹具/防变形支撑
-> 粗加工/粗磨/焊接前后处理
-> 孔预加工
-> 沉孔/攻牙
-> 外形/槽/台阶/型腔/放电/焊后机加工
-> 半精加工/精加工
-> 热处理/去应力
-> 热后恢复加工（校平/精磨/圆磨/精孔/回攻/喷砂/硬度检测）
-> 去毛刺/倒角/清洗
-> 表处前处理
-> 表面处理
-> 表处后处理/复检
-> 表面/镀层专项检验
-> 终检
-> 包装
```

细分排序映射：

| 排序段 | `sequence` | 工序编码 |
|---|---:|---|
| 来料/备料 | 18-20 | `raw_material_check`, `material_prepare` |
| 下料/开料 | 30-40 | `saw_cut`, `laser_cut_blank`, `laser_cut`, `weld_material_cut`, `wire_cut_blank` |
| 装夹/支撑 | 50-52 | `fixture_setup`, `soft_jaw_fixture`, `support_anti_deformation` |
| 粗加工/焊接前后处理 | 53-66 | `surface_grinding_rough`, `welding_prepare`, `fit_up`, `welding`, `weld_grinding`, `cnc_milling`, `cnc_rough_milling`, `turning`, `turning_rough`, `facing`, `center_drilling`, `wire_cut_profile` |
| 孔预加工/孔组检验 | 70-78 | `drilling`, `drilling_through`, `drilling_blind`, `side_hole_machining`, `pcd_hole_pattern`, `second_setup`, `reverse_side_machining`, `side_setup`, `pcd_hole_inspection` |
| 沉孔/攻牙/螺纹检验 | 80-95 | `countersink`, `counterbore`, `countersink_90`, `reverse_counterbore`, `tapping`, `tapping_through`, `blind_tapping`, `fine_thread_tapping`, `side_tapping`, `thread_inspection` |
| 外形/槽/型腔/焊后检查/过程检验 | 100-109 | `profile_milling`, `step_milling`, `slot_milling`, `pocket_milling`, `edm`, `post_weld_machining`, `weld_inspection`, `first_article_inspection`, `in_process_inspection` |
| 精加工 | 110-112 | `cnc_finish_milling`, `turning_finish`, `grooving_turning` |
| 热处理/去应力 | 120-121 | `heat_treatment`, `stress_relief` |
| 热后恢复/精孔/精度检验 | 130-139 | `straightening`, `finish_grinding`, `cylindrical_grinding`, `precision_hole`, `reaming`, `boring`, `precision_surface_finish`, `precision_hole_inspection`, `flatness_inspection`, `hardness_inspection` |
| 去毛刺/倒角/清洗 | 150-154 | `deburr`, `chamfer_turning`, `cleaning` |
| 表处前处理 | 160-164 | `pre_plating_cleaning`, `surface_masking`, `hard_chrome_masking`, `anodize_masking`, `powder_masking` |
| 表面处理 | 165-177 | `sand_blasting`, `chemical_nickel`, `clear_anodizing`, `hard_anodizing`, `color_anodizing`, `hard_chrome`, `powder_coating`, `white_powder_coating`, `powder_coating_texture` |
| 表处后处理/复检 | 182-187 | `dehydrogenation_bake`, `thread_chasing`, `post_anodize_reaming`, `post_chrome_polishing`, `post_surface_precision_hole_check` |
| 表面/镀层专项检验 | 188-190 | `coating_thickness_inspection`, `surface_inspection`, `post_chrome_inspection` |
| 终检 | 199 | `inspection` |
| 包装 | 200 | `protective_packaging` |
| 人工确认 | 890-900 | `unmapped_operation`；`manual_review` 只转为风险提示，不作为路线步骤输出 |

## 置信度

| 情况 | 置信度建议 |
|---|---|
| 明确规则命中且证据完整 | 0.85-1.0 |
| 规则命中但证据不完整 | 0.6-0.85 |
| AI 或候选推断 | 0.4-0.7 |
| 冲突未消解 | 低于 0.7 并待确认 |

## 不做什么

- 不计算工程量。
- 不计算价格。
- 不让 AI 将字典外工序作为正式可自动报价工序；AI 只能把明确证据识别到的字典外工序放入 `unmapped_operation` 复核通道。
- 不把解释文本当作规则依据。

## 验收标准

- 必选工序召回率 >= 90%。
- 工序误判率 <= 15%。
- 每个工序有触发原因。
- 每个工序有排序。
- 每个工序有置信度和待确认标记。

## AI Coding 注意事项

- 不要用自然语言判断替代规则表。
- 不要在没有证据时强行输出高置信度。
- 不要把工序顺序写散在多个地方，应集中维护。
- 不要让工序识别依赖页面字段。

