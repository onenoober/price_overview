# 工艺路线功能抽取

本文从当前代码中抽取“工艺阶段”和“详细工序”的实现口径，便于确认现有能力边界。

## 代码入口

- 阶段与详细工序主逻辑：`backend/app/process_recognition.py`
- 详细工序字典与报价归并：`backend/app/process_dictionary.py`
- 前端展示：`client/views/main_window.py`
- 数据契约：`docs/contracts/process_route.schema.json`

## 总体流程

当前工艺路线输出分两层：

1. `stage_route`：工艺阶段路线，是制造顺序骨架，不直接计价。
2. `operations`：详细工序/报价工序，是工程量和报价计算的依据。

规则路线流程：

```text
part_feature
  -> plan_process_stages()
  -> stage_route
  -> expand_stage_route_to_operations()
  -> operations
  -> synchronize_stage_route_with_operations()
  -> 给 operation 写入 stage_code/stage_name
  -> 给 stage_route 写入 actual_operation_codes
```

AI 自主路线流程：

```text
AI generate_process_route()
  -> 只允许输出 allowed_stage_codes 里的阶段
  -> add_ai_generated_stages() 校验阶段字典
  -> expand_stage_route_to_operations() 仍由后端规则展开详细工序
```

结论：AI 可以参与阶段骨架规划，但不能自由新增阶段，也不能直接输出自动报价的详细工序。详细工序仍以系统字典和规则为准。

## 阶段字典

阶段固定定义在 `STAGE_DEFINITIONS`，当前共有 16 个阶段。

| 阶段编码 | 阶段名称 | 作用 |
|---|---|---|
| `material_preparation` | 来料/备料 | 确认材料牌号、规格、毛坯状态并准备材料。 |
| `blanking` | 下料/开料 | 根据零件类型、毛坯尺寸和材料选择锯切、激光或线割开料。 |
| `fixture_and_datum` | 装夹/基准建立 | 确定装夹、找正、软爪/夹具、防变形支撑和加工基准。 |
| `rough_machining` | 主体粗加工 | 先建立主要基准、去除大余量、粗加工主体形状。 |
| `hole_machining` | 孔预加工 | 普通孔、侧孔、PCD孔组和螺纹底孔先行加工。 |
| `thread_and_counterbore` | 沉孔/攻牙 | 沉孔、反面沉孔、通牙、盲牙、细牙和侧面攻牙。 |
| `profile_and_cavity` | 外形/槽/型腔加工 | 加工外形轮廓、槽、台阶、型腔、放电区域和焊后安装面。 |
| `heat_and_stabilize` | 热处理/去应力 | 按图纸热处理或在粗精加工之间去应力、时效以稳定尺寸。 |
| `post_heat_correction` | 热后恢复加工 | 热处理后按变形、尺寸面、孔、螺纹、氧化皮和硬度验证安排恢复加工。 |
| `finish_and_precision` | 精加工/精孔 | 稳定后完成精铣、精车、精密面修正、精孔、铰孔和镗孔。 |
| `deburr_cleaning` | 去毛刺/倒角/清洗 | 去毛刺、倒角、锐角倒钝、清洗和去油去屑。 |
| `pre_surface` | 表处前处理 | 表处前清洗、遮蔽螺纹孔/精孔/功能面。 |
| `surface_treatment` | 表面处理 | 化学镍、阳极氧化、镀硬铬、喷塑、喷砂等表面处理。 |
| `post_surface` | 表处后处理/复检 | 表处后回攻清牙、除氢、复铰、修磨和精孔复检。 |
| `inspection` | 专项检验/终检 | 首件、过程、螺纹、精孔、膜厚、外观、平面度和终检。 |
| `packaging` | 防护包装 | 终检后进行防划伤、防弯曲、防锈和防碰伤包装。 |

## 阶段与详细工序对应

这里的“对应”是阶段允许包含的候选工序范围，即 `planned_operation_codes`。本次实际命中的工序会写入 `actual_operation_codes`。

| 阶段 | 当前候选详细工序 |
|---|---|
| 来料/备料 | `raw_material_check` 来料确认<br>`material_prepare` 备料 |
| 下料/开料 | `saw_cut` 锯切下料<br>`laser_cut_blank` 激光开料<br>`laser_cut` 激光切割<br>`weld_material_cut` 焊接件下料<br>`wire_cut_blank` 线割开料 |
| 装夹/基准建立 | `fixture_setup` 装夹/找正<br>`soft_jaw_fixture` 软爪/专用夹具<br>`support_anti_deformation` 防变形支撑<br>`second_setup` 二次装夹<br>`side_setup` 侧向装夹 |
| 主体粗加工 | `surface_grinding_rough` 平面粗磨<br>`cnc_milling` CNC铣削<br>`cnc_rough_milling` CNC粗铣<br>`turning` 车削<br>`turning_rough` 粗车<br>`facing` 车端面<br>`center_drilling` 打中心孔<br>`fit_up` 组对/点焊定位<br>`welding` 焊接<br>`weld_grinding` 焊缝打磨 |
| 孔预加工 | `drilling` 钻孔<br>`drilling_through` 钻通孔<br>`drilling_blind` 钻盲孔<br>`side_hole_machining` 侧面孔加工<br>`pcd_hole_pattern` PCD孔组加工<br>`reverse_side_machining` 翻面加工 |
| 沉孔/攻牙 | `countersink` 沉孔/沉头孔<br>`counterbore` 圆柱沉孔<br>`countersink_90` 90度沉头孔<br>`reverse_counterbore` 反面沉孔<br>`tapping` 攻牙<br>`tapping_through` 攻通牙<br>`blind_tapping` 盲孔攻牙<br>`fine_thread_tapping` 细牙攻牙<br>`side_tapping` 侧面攻牙 |
| 外形/槽/型腔加工 | `profile_milling` 外形轮廓铣削<br>`step_milling` 台阶/沉台加工<br>`slot_milling` 槽加工<br>`pocket_milling` 型腔/凹槽加工<br>`edm` 放电加工<br>`post_weld_machining` 焊后机加工<br>`wire_cut_profile` 线切割外形 |
| 热处理/去应力 | `heat_treatment` 热处理<br>`stress_relief` 去应力 |
| 热后恢复加工 | `straightening` 校平/校直<br>`cnc_finish_milling` CNC精铣<br>`precision_surface_finish` 精密面修正<br>`finish_grinding` 精磨<br>`cylindrical_grinding` 圆磨<br>`precision_hole` 精孔加工<br>`reaming` 铰孔<br>`boring` 镗孔<br>`thread_chasing` 回攻/清牙<br>`sand_blasting` 喷砂<br>`cleaning` 清洗<br>`hardness_inspection` 硬度检测 |
| 精加工/精孔 | `cnc_finish_milling` CNC精铣<br>`turning_finish` 精车<br>`grooving_turning` 车槽<br>`precision_surface_finish` 精密面修正<br>`precision_hole` 精孔加工<br>`reaming` 铰孔<br>`boring` 镗孔 |
| 去毛刺/倒角/清洗 | `deburr` 去毛刺/倒角<br>`chamfer_turning` 车削倒角<br>`cleaning` 清洗 |
| 表处前处理 | `pre_plating_cleaning` 镀前清洗<br>`surface_masking` 表处遮蔽<br>`hard_chrome_masking` 镀硬铬遮蔽<br>`anodize_masking` 阳极氧化遮蔽<br>`powder_masking` 喷塑遮蔽<br>`welding_prepare` 焊前处理 |
| 表面处理 | `sand_blasting` 喷砂<br>`chemical_nickel` 化学镍<br>`clear_anodizing` 本色阳极氧化<br>`hard_anodizing` 硬质阳极氧化<br>`color_anodizing` 着色阳极氧化<br>`hard_chrome` 镀硬铬<br>`powder_coating` 喷塑<br>`white_powder_coating` 白色喷塑<br>`powder_coating_texture` 小桔纹喷塑 |
| 表处后处理/复检 | `dehydrogenation_bake` 除氢处理<br>`thread_chasing` 回攻/清牙<br>`post_anodize_reaming` 氧化后复铰<br>`post_chrome_polishing` 镀硬铬后抛光/修磨<br>`post_surface_precision_hole_check` 表处后精孔复检 |
| 专项检验/终检 | `pcd_hole_inspection` PCD孔组检验<br>`thread_inspection` 螺纹检验<br>`weld_inspection` 焊缝检验<br>`first_article_inspection` 首件检验<br>`in_process_inspection` 过程检验<br>`precision_hole_inspection` 精孔检验<br>`flatness_inspection` 平面度检验<br>`coating_thickness_inspection` 膜厚检验<br>`surface_inspection` 表面检验<br>`post_chrome_inspection` 镀硬铬后检验<br>`inspection` 终检 |
| 防护包装 | `protective_packaging` 防护包装 |

## 详细工序字典能力

每个详细工序由 `ProcessDefinition` 定义，核心字段如下：

| 字段 | 含义 |
|---|---|
| `process_code` | 详细工序编码。 |
| `process_name` | 工序中文名。 |
| `process_type` | 工序类型，如材料、下料、机加工、孔加工、表面处理、检验。 |
| `sequence` | 工序排序依据。 |
| `requires_manual_confirm` | 是否天然需要人工确认。 |
| `auto_quote_enabled` | 是否可以自动报价。 |
| `quantity_type` | 工程量类型，如重量、孔数、面积、工时。 |
| `pricing_unit` | 报价单位，如 kg、hole、m2、hour、pcs。 |
| `quote_process_code` | 报价归并编码。例如 `cnc_rough_milling`、`fixture_setup` 会归并到 `cnc_milling` 计价。 |
| `aliases` | 识别别名。 |

也就是说，详细工序比报价工序更细；报价时可以把多个细分工序归并到同一个主报价工序。

## 规则触发范围

当前路线规则主要读取 `part_feature` 中这些信息：

- 材料：是否模具钢、工具钢、不锈钢、铝等。
- 几何：零件类型、包络尺寸、薄板/薄壁/长条件、轴类、复杂度。
- 孔特征：通孔、盲孔、沉孔、反面沉孔、螺纹孔、精孔、PCD孔组。
- 技术要求：热处理、表面处理、去毛刺、粗糙度、平面度、紧公差、未标尺寸参见3D。
- 风险继承：解析风险、特征融合风险。

主要规则函数：

- `plan_process_stages()`：规划阶段骨架。
- `expand_stage_route_to_operations()`：按阶段和特征展开详细工序。
- `add_shape_operations()`：装夹、CNC、外形、薄板、轴类、复杂件相关工序。
- `add_hole_operations()`：孔、沉孔、螺纹、精孔相关工序。
- `add_requirement_operations()`：热处理、表处、去毛刺、技术要求相关工序。
- `add_stage_anchor_operations()`：阶段有了但缺少关键工序时补候选，例如热处理/热后恢复。
- `synchronize_stage_route_with_operations()`：把详细工序回填到阶段，并生成一致性风险。

## 一致性规则

阶段和详细工序不是一一必然展开。

- `planned_operation_codes`：该阶段理论上可能包含的工序范围。
- `actual_operation_codes`：本次真实命中的工序。
- 如果阶段已规划，但没有展开出任何对应详细工序，会打 `STAGE_WITHOUT_OPERATION` 风险。
- 如果详细工序无法映射到阶段，会打 `OPERATION_WITHOUT_STAGE` 风险。

这也是为什么界面可能出现“阶段有主体粗加工，但详细工序没有CNC粗铣”的情况：阶段是骨架，详细工序需要具体规则证据命中。

## 当前功能边界

- 阶段字典是固定的，不支持 AI 或规则自由新增阶段。
- AI 自主路线只能选已有阶段编码，不能输出自动报价工序。
- 详细工序必须在 `PROCESS_DEFINITIONS` 中登记，否则只能进入 `unmapped_operation` 复核通道。
- 缺少 STEP 零件类型和包络尺寸时，规则会倾向保守：可能规划阶段，但不自动落具体粗加工/下料工序。
- “热后恢复加工”是阶段，不等于一定有“校平/校直”；校平需要明确校平/校直、薄板、薄壁、长条件或变形风险证据。
- “外形轮廓铣削/线切割外形”当前归在“外形/槽/型腔加工”，不是“主体粗加工”阶段的默认必出工序。

