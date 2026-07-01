# 路线引擎 v2 根因修复开发方案

## 目标

针对 16 组 PDF+STEP 回归样件暴露的问题，本方案不继续做逐件补丁，而是从根因层修复：

- `84398`：钣金/焊接支撑架不能因标题栏 `方件类` 静默走机加。
- `84311`：滚筒/轴类不能因标题栏 `方件类` 静默走机加。
- `83951`：小钣金支架不能漏 `bending`。
- `83722/83684`：普通槽/长条不能膨胀成 `wire_cut_profile/edm/pocket_milling`。
- 普通机加/铝件不能轻易加入 `surface_grinding_rough`。

核心原则：

1. 标题栏字段要先解析正确。
2. 小类决策不能让单一字段一票定族。
3. 几何纠偏应发生在 L0/L0.5，而不是 L1 路由后硬改族。
4. 工序只能由强证据触发，普通特征不能放大成特殊加工。
5. 用 16 件黄金回归集固化结果，避免后续回归。

## PR1：标题栏字段边界重构

涉及文件：

- `backend/app/parser_service.py`
- `backend/tests/test_pdf_part_type.py`

### 背景

当前仍有 `投 影` 被识别为零件名的问题：

- `RM-JJ-00083816-01` 实际名称为 `垫圈`，系统识别为 `投 影`。
- `RM-JJ-00084311-01` 实际名称为 `滚筒`，系统识别为 `投 影`。

根因是标题栏解析仍依赖候选文本推断，没有稳定识别图框中“标签-值”的语义边界。

### 方案

在 `parser_service.py` 中增强标题栏解析逻辑：

- 识别标题栏标签：
  - `材料`
  - `表面处理`
  - `热处理`
  - `重量`
  - `物件料号`
  - `零件类型`
  - `设计`
  - `审核`
  - `批准`
  - `投影`
  - `比例`
- 每个标签只从稳定相邻格子取值。
- `part_name` 优先从标题栏名称格取值，而不是从右下角中文块里选最长文本。
- 明确排除以下内容作为零件名：
  - `投影`
  - 公司名
  - 设计者/审核者/批准者
  - 日期
  - 标题栏标签文本
  - 材料、表处、热处理、重量、比例等字段值

### 测试

新增或补充测试：

```python
def test_projection_label_is_not_part_name(self):
    self.assertTrue(looks_like_non_part_name("投 影"))

def test_83816_title_block_part_name_is_washer(self):
    # RM-JJ-00083816-01 标题栏名称应识别为 垫圈
    ...

def test_84311_title_block_part_name_is_roller(self):
    # RM-JJ-00084311-01 标题栏名称应识别为 滚筒
    ...
```

### 验收

- `83816` 名称为 `垫圈`，不是 `投 影`。
- `84311` 名称为 `滚筒`，不是 `投 影`。
- `84398` 名称保持 `输送支撑架`。
- 之前已修的标题栏负例不回归：
  - `郭江峰`
  - `调质HB220-280`
  - `色号:PANTONE427C`
  - `M8螺母座`
  - `M6深10`

## PR2：小类决策器重构

涉及文件：

- `backend/app/part_feature_builder.py`
- `backend/app/domain_v2/route_engine/router.py`
- `backend/tests/test_pdf_part_type.py`
- `backend/tests/test_route_engine_router.py`

### 背景

当前 L1 router 信任 `pdf_part_category`，这本身是对的。但如果标题栏小类本身被抽错或与几何/名称强冲突，就会静默走错族：

- `84398`：`assembly_candidate + 输送支撑架 + Q235A + 喷塑`，却因标题栏 `方件类` 走 `MACHINING`。
- `84311`：`roller_candidate + 滚筒 + 圆柱几何`，却因标题栏 `方件类` 走 `MACHINING`。
- `83684`：机加目录下 `480 x 40 x 16` 长条小件，标题栏 `大板类` 导致路线过重。

### 原则

保持“L1 不让 STEP 几何直接换族”的铁律。纠偏应在 L0/L0.5 完成，即在 `build_part_feature()` 阶段生成更可信的 `pdf_part_category` 或强复核风险。

### 方案

新增或增强：

```python
def refine_pdf_part_category(pdf_result, step_result, geometry, material, part_name):
    ...
```

输出建议：

```python
{
    "category_name": "钣金类",
    "confidence": 0.72,
    "raw_text": "...",
    "source": {...},
    "refinement_rule": "ASSEMBLY_SHEET_METAL_BY_NAME_GEOMETRY",
    "requires_review": True,
}
```

### 规则 1：钣金/焊接候选

满足以下强信号时，应纠偏为 `钣金类/焊接类`，或触发强复核：

- STEP `part_type == "assembly_candidate"`。
- 名称含：
  - `支撑架`
  - `支架`
  - `框架`
  - `脚踏台`
  - `护罩`
- 材料含：
  - `Q235`
  - `Q235A`
  - `SPCC`
  - `SUS`
- 表处含：
  - `喷塑`
  - `喷粉`
  - `粉末喷涂`

目标样件：

- `RM-JJ-00084398-01`

### 规则 2：轴/滚筒候选

满足以下强信号时，应纠偏为 `圆件类`，或触发强复核：

- STEP `part_type` 为：
  - `roller_candidate`
  - `shaft_candidate`
  - `shaft`
- 名称含：
  - `滚筒`
  - `轴`
  - `垫圈`
  - `圆钢`
  - `套`
- bbox 近圆柱：
  - 两个截面方向尺寸接近。
  - 第三个方向明显为长度或厚度。

目标样件：

- `RM-JJ-00084311-01`
- `RM-JJ-00083816-01`
- `RM-JJ-00083848-01`

### 规则 3：大板边界

`大板类` 不应仅由标题栏字段一票定族。建议判断：

- 强大板：
  - `longest >= 800`
  - 或 `aspect >= 6~8` 且名称含 `底板/顶板/推料板/背板/长板`
- 边界件：
  - `300 <= longest < 800`
  - aspect 较大但尺寸不属于超长大板
  - 目录/名称更像机加小件

边界件建议走 `CATEGORY_CONFLICT_REQUIRES_REVIEW`，不要静默加 `large_plate_roughing/stress_relief/straightening`。

目标样件：

- `RM-JJ-00083684-01`

### 新增风险码

建议新增：

- `CATEGORY_REFINED_BY_GEOMETRY_AND_NAME`
- `CATEGORY_CONFLICT_REQUIRES_REVIEW`
- `ASSEMBLY_SHEET_METAL_CATEGORY_REVIEW`
- `TURNING_GEOMETRY_CATEGORY_REVIEW`
- `LARGE_PLATE_BOUNDARY_REVIEW`

### 验收

- `84398` 不再静默走 `MACHINING`。
- `84311` 不再静默走 `MACHINING`。
- `83684` 不再静默过度大板化，至少触发强复核。

## PR3：钣金折弯与焊接证据补强

涉及文件：

- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/domain_v2/route_engine/policy.py`
- `backend/app/domain_v2/route_engine/skeleton.py`
- `backend/tests/test_route_assertions.py`

### 折弯证据

`bending` 继续不放入钣金骨架，必须由证据触发。

证据来源：

- PDF 明确出现：
  - `折弯`
  - `折边`
  - `展开`
  - `弯曲半径`
  - `bend`
  - `bending`
- STEP 显示明显非平板高度。
- PDF 小类为钣金，名称含 `支架/护罩`，且 bbox 具有 L 形/Z 形/立体支架特征。
- `assembly_candidate` 钣金件可作为折弯强候选，但仍需人工复核。

平板保护：

- 长宽大、厚度 3~6 mm。
- 无立体高度。
- 无折弯/成形文本。
- 不应加 `bending`。

目标样件：

- `83254`：应有 `bending`。
- `83951`：应补 `bending`。
- `83938`：无明确折弯证据时不强加。

### 焊接证据

强焊接证据：

- `assembly_candidate`
- PDF 小类或纠偏小类为钣金/焊接类
- 名称含：
  - `支撑架`
  - `框架`
  - `脚踏台`
  - `焊接件`
- 材料/表处匹配：
  - `Q235/SPCC/SUS`
  - `喷塑/喷粉/粉末喷涂`

注意事项：

- 条件焊接模板句继续只输出 `WELDING_CONDITIONAL_TEXT`。
- `assembly_signal` 命中后只能 append 焊接候选，不能 return。
- 必须继续扫描技术要求，让条件焊接复核风险仍然保留。

目标样件：

- `84398` 应输出 `sheet_metal_welding`。

### 验收

- `83951` 含 `bending`。
- `83254` 仍含 `bending`。
- `83938` 无强证据时不强加 `bending`。
- `84398` 含：
  - `laser_cut_blank`
  - `bending`
  - `sheet_metal_welding`
  - `powder_coating_texture`

## PR4：特殊加工门控收紧

涉及文件：

- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/domain_v2/route_engine/policy.py`
- `backend/tests/test_route_assertions.py`

### 背景

当前普通槽或复杂度可能放大为：

- `slot_milling`
- `pocket_milling`
- `wire_cut_profile`
- `edm`

典型问题：

- `83722`：6061 长条底板，普通槽被扩展到 `wire_cut_profile/edm`。
- `83684`：长条小件加入 `wire_cut_profile/edm/pocket_milling`，路线过重。

### 方案

拆分特殊加工证据：

#### `slot_milling`

允许由以下证据触发：

- STEP `slot_count > 0`
- PDF 槽标注
- 名称/技术要求中有槽加工

#### `pocket_milling`

必须有更强证据：

- 明确型腔/凹腔。
- 有深度。
- 有封闭区域面积。
- STEP 能识别 pocket 特征。

普通槽不得触发 `pocket_milling`。

#### `wire_cut_profile`

必须有强证据：

- PDF 明确 `线切割`。
- STEP 有贯穿异形内轮廓。
- 深窄封闭轮廓不适合普通铣削。

普通外形、普通槽不得触发。

#### `edm`

必须有强证据：

- PDF 明确 `电火花/放电`。
- 深窄清角。
- 深腔小 R。
- 普通铣削无法加工的内角。

普通 6061 长条槽不得触发。

### 验收

- `83722` 不应出现 `wire_cut_profile/edm`，普通槽最多 `slot_milling`。
- `83684` 不应默认出现 `wire_cut_profile/edm/pocket_milling`。
- 真正有线切割/EDM 强证据的旧样件仍能触发对应工序。

## PR5：平面磨证据门槛收紧

涉及文件：

- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/tests/test_route_assertions.py`

### 背景

当前 `surface_grinding_rough` 在多件方件/铝件上偏积极：

- `83374`
- `83726`
- `84245`
- `83722`
- `84089`

多数图纸没有明确平面磨要求，仅有通用公差表或普通孔/槽加工。

### 允许触发条件

`surface_grinding_rough` 只应由强证据触发：

- PDF 明确写：
  - `磨`
  - `平面磨`
  - `研磨`
  - `磨削`
- 明确平面度要求。
- 明确高粗糙度要求且作用于平面。
- 材料/工艺组合支持：
  - 45 钢
  - 镀硬铬
  - 大板长条
  - 有平面度/配合面要求

### 不应触发条件

- 仅有标题栏通用公差表。
- 仅有普通孔/槽。
- 6061 + 喷砂阳极 + 普通未注公差。
- 小方件无平面度/粗糙度强标注。

### 验收

- `83374/83726/84245` 默认不含 `surface_grinding_rough`。
- `83722/84089` 不因 6061 长条和普通公差自动加平面磨。
- `83702/83711` 可保留或复核，因为是 45 钢长条大板 + 镀硬铬。

## PR6：16 件黄金回归集

涉及文件：

- `backend/tests/data/route_engine_snapshot_batch4.json`
- `backend/tests/test_route_snapshot_batch4.py`
- `run_test_routes.py` 或新增 `run_test_routes_batch4.py`

### 样件

钣金：

- `RM-JJ-00083938-01`
- `RM-JJ-00083254-01`
- `RM-JJ-00084398-01`
- `RM-JJ-00083951-01`

大板：

- `RM-JJ-00083702-01`
- `RM-JJ-00083711-01`
- `RM-JJ-00083722-01`
- `RM-JJ-00084089-01`

机加：

- `RM-JJ-00083374-01`
- `RM-JJ-00083684-01`
- `RM-JJ-00083726-01`
- `RM-JJ-00084245-01`

轴类：

- `RM-JJ-00083692-01`
- `RM-JJ-00083816-01`
- `RM-JJ-00083848-01`
- `RM-JJ-00084311-01`

### 关键断言

#### 84398

- family 应为 `SHEET_METAL` 或钣金焊接路线。
- 必须含：
  - `laser_cut_blank`
  - `bending`
  - `sheet_metal_welding`
  - `powder_coating_texture`
- 不应含：
  - `cnc_rough_milling`
  - `surface_grinding_rough`

#### 84311

- 应走 `TURNING`。
- 必须含：
  - `turning`
  - `chemical_nickel`
- 不应含 CNC 主线。

#### 83951

- 必须含 `bending`。

#### 83722

- 不应含：
  - `wire_cut_profile`
  - `edm`

#### 83684

- 不应静默过度大板化。
- 如果仍被识别为大板，必须出现 `LARGE_PLATE_BOUNDARY_REVIEW` 或类似强复核风险。

#### 通用断言

- 非回转件不含 `cylindrical_grinding`。
- `本色氧化，喷砂` 继续输出：
  - `sand_blasting`
  - `clear_anodizing`
- 钣金条件焊接模板句只输出 `WELDING_CONDITIONAL_TEXT`，除非有 assembly 强证据。

## 推荐实施顺序

1. PR1 标题栏字段边界。
   - 先解决 `投 影` 串入零件名。
2. PR2 小类决策器。
   - 解决 84398、84311、83684 的根因。
3. PR3 钣金折弯/焊接证据。
   - 解决 83951 和 84398 主路线。
4. PR4 特殊加工门控。
   - 解决 83722、83684 的 `wire/edm/pocket` 膨胀。
5. PR5 平面磨门槛。
   - 解决普通方件/铝件 `surface_grinding_rough` 偏积极。
6. PR6 黄金回归集。
   - 固化 16 件样件，防止后续回归。

## 最终验收标准

- 84398 不再走机加主线，改为钣金焊接/喷塑路线。
- 84311 不再走机加主线，改为滚筒/轴类路线。
- 83951 补上折弯。
- 83722/83684 不再自动膨胀出线切割/EDM。
- 普通方件/铝件不因通用公差或复杂度默认加平面磨。
- 83816/84311 标题栏名称不再解析为 `投 影`。
- 已修复能力不回退：
  - 非回转件无外圆磨。
  - 大板长条仍能触发防变形复核。
  - 轴类真实孔仍能恢复。
  - 复合表处仍能输出多工序。

