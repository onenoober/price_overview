# 路线引擎 V2 系统性修复开发文档

## 1. 背景

本轮 17 套 PDF+STEP 实测暴露出路线引擎的结构性问题：

- V2 大类路由基本正确，但输出偏“阶段路线”，硬铬后处理、精孔/镀后孔检、热处理硬度检验、轴类直线度检查等细项不足。
- legacy 细项召回很多，但误报严重，尤其会给钣金件混入 CNC、线切割、电火花、应力释放等不合适工序。
- 部分钣金折弯依赖证据过弱时会漏；大板规则对 6061 长条板偏重；表处理后处理链没有在 V2 中完整展开。

根因不是某条规则写错，而是当前系统缺少一个“主路线到详细报价项”的可控展开层。V2 解决了族路由的误判，但为了避免 legacy 膨胀，过度压缩了细项；legacy 有细项知识，但没有足够的族门控和证据强度约束。

本方案目标是把 V2 扩展成三层输出：

1. `primary_route`：稳定、短、可报价的大类主路线。
2. `detail_ops`：有强证据支持的详细工序，用于报价展开和工艺复核。
3. `review_candidates`：证据不足或可能误报的候选，只提示人工复核，不直接计入默认报价。

## 2. 设计原则

1. 保持 V2 的族路由铁律：L1 仍以业务小类为主，STEP 几何不能在 L1 后直接换族，只能在 L0/L0.5 阶段参与小类修正或产生复核。
2. 禁止恢复 legacy 式“全量追加”。legacy 规则只能迁移为有族约束、有证据强度、有适用条件的 V2 规则。
3. 新增细项必须有输出等级：强证据进 `detail_ops`，弱证据进 `review_candidates`，不要把不确定项混进默认报价路线。
4. 每个修复必须有反向守门测试：修漏报时同时防止误报，修误报时同时防止真实工序丢失。
5. 系统输出应可解释：每个详细工序都必须带 `source_layer`、`rule_code`、`evidence_strength`、`review_reason`。

## 3. 当前架构诊断

### 3.1 V2 为什么大类准

`backend/app/domain_v2/route_engine/router.py` 中 `route_family()` 采用业务小类硬路由：

- `钣金类/焊接类` -> `SHEET_METAL`
- `大板类` -> `LARGE_PLATE`
- `方件类` -> `MACHINING`
- `圆件类` -> `TURNING`

当 STEP 几何和 PDF 小类冲突时，只产生 `CATEGORY_GEOMETRY_CONFLICT_REVIEW`，不切换族。这避免了 STEP 将钣金误判为复杂块后走机加工主线。

### 3.2 V2 为什么不够细

`backend/app/domain_v2/route_engine/skeleton.py` 的骨架只包含必经工序。例如：

- `SHEET_METAL` 只有来料、激光、去毛刺、检验、包装。
- `MACHINING` 只有锯切、装夹、粗铣、精铣、去毛刺、检验、包装。
- `TURNING` 只有锯切、车削、去毛刺、检验、包装。
- `LARGE_PLATE` 默认包含大板粗加工、大板精加工、平面度检查。

折弯、焊接、孔加工、攻丝、热处理、硬铬、精孔、磨削、镀后检查等都依赖 `evidence.py` 生成候选，再由 `policy.py` 矩阵放行。

### 3.3 legacy 为什么误报多

`backend/app/process_recognition.py` 是旧规则集中地。它会基于孔、槽、复杂度、材料、表处理、技术要求持续追加工序，缺少严格族门控。它包含不少有价值的后处理知识，但也会把钣金件推入 CNC/EDM/线切割/应力释放等不适合的路线。

## 4. 目标架构

### 4.1 新增路线分层模型

建议在 V2 route dict 中增加以下字段，保留现有 `operations` 兼容前端和报价：

```json
{
  "operations": [],
  "primary_route": [],
  "detail_ops": [],
  "review_candidates": [],
  "post_process_plan": [],
  "route_explain": {
    "family": "SHEET_METAL",
    "routing_basis": "pdf_business_category",
    "geometry_conflict": false
  }
}
```

兼容策略：

- `operations` 暂时继续输出主路线 + 强证据详细工序，避免破坏现有报价。
- `primary_route` 固定来自 skeleton。
- `detail_ops` 收纳强证据细项，后续报价可逐步切换使用。
- `review_candidates` 只展示和复核，不默认计价。
- `post_process_plan` 专门放表处理/热处理后的依赖链。

### 4.2 工序证据等级

在 `Candidate` 中增加或标准化：

```python
evidence_strength: Literal[
    "required",
    "strong_field",
    "strong_geometry",
    "explicit_text",
    "derived_process",
    "weak_text",
    "risk_candidate",
]
route_effect: Literal[
    "primary",
    "detail",
    "review_only",
]
```

映射建议：

| 证据等级 | 默认去向 | 示例 |
| --- | --- | --- |
| `required` | `primary_route` | 族骨架必经工序 |
| `strong_field` | `detail_ops` | 标题栏表处理“镀硬铬” |
| `strong_geometry` | `detail_ops` | STEP 明确 assembly_candidate 触发焊接 |
| `explicit_text` | `detail_ops` | 图纸明确“淬火 HRC45-50” |
| `derived_process` | `detail_ops` 或 `post_process_plan` | 硬铬 -> 除氢/镀后抛光 |
| `weak_text` | `review_candidates` | 通用技术要求中的条件焊接 |
| `risk_candidate` | `review_candidates` | 长条大板可能校直 |

## 5. P0 修复：硬铬与表处理后处理链

### 5.1 问题

V2 能输出 `hard_chrome`，但没有展开：

- 镀前清洗
- 镀前遮蔽
- 镀硬铬
- 除氢
- 镀后抛光/修磨
- 镀后精孔/螺纹复检
- 镀层厚度/外观检查

legacy 有这些知识，但当前没有被安全迁移。

### 5.2 设计

新增模块：

```text
backend/app/domain_v2/route_engine/post_process.py
```

职责：

- 根据已经进入路线的表处理/热处理/精孔/螺纹/材料，生成后处理依赖。
- 不直接读取 PDF 原文，只消费 `ParsedPart` 和已通过矩阵的 ops。
- 所有派生工序标记 `evidence_strength="derived_process"`。

核心函数：

```python
def expand_post_process_dependencies(
    *,
    family: str,
    parsed: ParsedPart,
    accepted_ops: list[OpSpec],
) -> tuple[list[OpSpec], list[Review]]:
    ...
```

硬铬规则：

```python
if has_op("hard_chrome"):
    add("pre_plating_cleaning", detail)
    add("hard_chrome_masking", detail_or_review)
    add("dehydrogenation_bake", detail if steel_or_40cr else review)
    add("post_chrome_polishing", detail if turning_or_precision_surface else review)
    add("coating_thickness_inspection", detail)
    add("surface_inspection", detail)
    add("post_chrome_inspection", detail)

    if has_precision_hole_or_thread:
        add("post_surface_precision_hole_check", detail)
        add("thread_chasing", detail if has_thread else review)
```

族约束：

- `SHEET_METAL`：硬铬少见，除非明确字段，否则进入 review。
- `LARGE_PLATE/MACHINING/TURNING`：硬铬后处理可进 detail。
- `TURNING + hard_chrome`：优先加入镀后外圆抛光/尺寸复检。

### 5.3 验收

应补足：

- `RM-JJ-00083694-01`
- `RM-JJ-00083711-01`
- `RM-JJ-00083683-01`
- `RM-JJ-00083826-01`
- `RM-JJ-00083820-01`
- `RM-JJ-00083835-01`
- `RM-JJ-00083857-01`
- `RM-JJ-00084313-01`

守门：

- 没有 `hard_chrome` 的件不得出现 `hard_chrome_masking/dehydrogenation_bake/post_chrome_polishing`。
- 钣金喷塑件不得因通用技术要求误入硬铬后处理链。

## 6. P0 修复：热处理后检测与恢复加工

### 6.1 问题

V2 能识别 `heat_treatment`，但热处理后的硬度检验、变形复核、精磨/精车恢复加工没有稳定展开。

### 6.2 规则

新增到 `post_process.py`：

```python
if has_op("heat_treatment"):
    add("hardness_inspection", detail)

    if family in {"TURNING"} and has_hard_chrome_or_precision_surface:
        add("cylindrical_grinding", detail)

    if is_long_thin_or_plate and material_has_distortion_risk:
        add("straightening", review_candidate)

    if has_precision_hole:
        add("precision_hole_inspection", detail)
```

材料约束：

- `40Cr/S45C/45/SKD/Cr12` 等可触发热处理后检查。
- `6061-T6` 不因 T6 自动触发 `heat_treatment` 或 `hardness_inspection`。

### 6.3 验收

- `RM-JJ-00083835-01`、`RM-JJ-00083857-01` 应有 `heat_treatment + hardness_inspection`。
- 未标热处理的 45 钢硬铬件不应凭材料自动加 `heat_treatment`。
- 6061 氧化件不得出现热处理后检查。

## 7. P0 修复：钣金折弯证据增强

### 7.1 问题

折弯不再是钣金骨架必经项是正确的，否则纯托板会误报。但当前折弯证据不足时，真实支架可能漏 `bending`。

### 7.2 规则

保留 `SHEET_METAL` skeleton 不含 `bending`。

增强 `evidence._add_bending_evidence()`：

强证据进入 `detail_ops`：

- PDF 明确出现 `折弯/折边/展开/弯曲半径/bend/bending`。
- STEP `part_type` 为 `formed_sheet/bent_sheet/assembly_candidate`。
- PDF 类别为钣金，且名称含 `支架/护罩/支撑架/框架`，bbox 明显非纯平板。

弱证据进入 `review_candidates`：

- 名称像支架，但 STEP 几何为 `complex_block`。
- 图纸三视图存在厚度侧视，但文字层无折弯字段。

纯平板保护：

- 最小尺寸 <= 6mm，最大/中间尺寸形成平板，且无折弯文本、无成形几何，不加 `bending`。

### 7.3 本批样件期望

- `RM-JJ-00083917-01`：至少进入折弯复核；若名称/三视图规则足够强，可直接加 `bending`。
- `RM-JJ-00083381-01`、`RM-JJ-00084158-01`、`RM-JJ-00084346-01`：保留 `bending`。
- `RM-JJ-00083980-01`：纯托板不应加 `bending`。

## 8. P0 修复：大板规则按材料和风险裁剪

### 8.1 问题

`LARGE_PLATE` 骨架默认包含大板粗精加工和平面度检查，证据层又容易给长条板加 `stress_relief/straightening`。对 45 钢硬铬大板合理，对 6061 喷砂氧化长条偏重。

### 8.2 设计

把大板分成三个 profile：

```python
LARGE_PLATE_HEAVY_STEEL
LARGE_PLATE_ALUMINUM_STRIP
LARGE_PLATE_GENERAL
```

分类依据：

- `HEAVY_STEEL`：45/40Cr/钢件 + 硬铬/高平面度/长宽大于阈值。
- `ALUMINUM_STRIP`：6061/铝 + 长条 + 喷砂/阳极 + 无高精度平面度。
- `GENERAL`：其他大板。

骨架调整建议：

- `HEAVY_STEEL`：保留粗加工、精加工、平面度检查；允许去应力/校直进入 detail 或 review。
- `ALUMINUM_STRIP`：主路线用 `large_plate_roughing/large_plate_finishing`，但 `stress_relief/straightening/flatness_inspection` 降级为 review，除非 PDF 明确要求。
- `GENERAL`：保持现状但要求风险提示。

### 8.3 本批样件期望

- `RM-JJ-00083694-01`、`RM-JJ-00083711-01`：钢制硬铬大板，保守路线合理。
- `RM-JJ-00083722-01`、`RM-JJ-00084089-01`：6061 长条，`stress_relief/straightening` 默认进入复核，不直接作为强 detail。

## 9. P1 修复：精孔、孔检与镀后孔检

### 9.1 问题

PDF 文字层编码、孔标注拆分、STEP 孔识别噪声都会影响 `is_precision_hole`。V2 当前对精孔采取“能识别才加”，但缺少弱证据复核和后处理联动。

### 9.2 规则

新增孔证据归一：

```python
def classify_hole_evidence(hole, pdf_text, step_summary) -> HoleEvidence:
    ...
```

分类：

- `ordinary_hole`
- `thread_hole`
- `counterbore`
- `countersink`
- `precision_hole`
- `noise_hole`
- `uncertain_hole`

强精孔信号：

- H7/H8/G6 等配合公差。
- `铰孔/精孔/配合孔/定位孔`。
- Ra <= 0.8 且作用于孔。

弱信号：

- PDF 正则抽到 H7，但上下文不完整。
- STEP 孔很多但 PDF 无明确孔标注。

路线规则：

- 强信号：加 `precision_hole` 或 `reaming`，并加 `precision_hole_inspection`。
- 弱信号：进入 `review_candidates`。
- 若同时存在表处理，尤其硬铬/阳极：加 `post_surface_precision_hole_check` 或复核。

### 9.3 守门

- 不得把所有普通孔升级为精孔。
- 不得因 PDF 通用公差表中的 H7 示例误触发精孔。

## 10. P1 修复：轴类直线度、外圆磨与外螺纹

### 10.1 问题

轴类 V2 能走 `turning`，但长轴直线度/校直复核不足；硬铬轴类应有外圆磨/镀后尺寸复检；外螺纹有时会被误映射为 `tapping`。

### 10.2 规则

轴类长径比：

```python
length_diameter_ratio = longest / max(middle, shortest)
```

- `ratio >= 10`：加入 `straightness_inspection` 或 `straightening` review。
- `ratio >= 15`：校直复核优先级提高。

外圆磨：

- `TURNING + hard_chrome`：加 `cylindrical_grinding` 或镀后抛磨 detail。
- `TURNING + heat_treatment`：根据精度/表处理加 `cylindrical_grinding`。

外螺纹：

- 新增或启用 `external_thread_turning`。
- PDF 命中 `外螺纹/车螺纹/螺杆/external thread` 时不得映射为 `tapping`。
- 内螺纹孔才触发 `tapping`。

### 10.3 本批样件期望

- `RM-JJ-00084313-01`：长轴应有直线度/校直复核。
- `RM-JJ-00083820-01`、`RM-JJ-00084313-01`：硬铬轴类应有外圆磨或镀后抛磨/尺寸复核。
- 无明确内螺纹时不得强加 `tapping`。

## 11. P1 修复：表处理复合解析

### 11.1 问题

复合表处理如“本色氧化，喷砂”需要同时输出 `sand_blasting + clear_anodizing`。目前系统已有部分 plural 支持，但需统一到 V2 evidence 层和后处理层。

### 11.2 规则

统一使用：

```python
surface_treatment_operation_codes(requirement, material=..., family=...)
```

要求：

- 支持多 op 返回。
- 标题栏字段为强证据。
- 技术要求中的条件句为弱证据或复核。
- `PANTONE + Q235/SPCC + SHEET_METAL` 可推断喷塑，但 `PANTONE` 单独出现不推断。
- 孤立 `D` 不应触发表处理。

### 11.3 守门

- `RM-JJ-00083722-01`、`RM-JJ-00084089-01`：应同时有 `sand_blasting + clear_anodizing`。
- `RM-JJ-00083980-01`：表面字段 `D` 不应触发表处理。
- Q235 钣金喷塑色号应输出粉末喷涂。

## 12. P1 修复：legacy 知识迁移清单

从 `process_recognition.py` 迁移，但必须重写为 V2 规则：

| legacy 能力 | 迁移目标 | 默认等级 |
| --- | --- | --- |
| 表处理后依赖工序 | `post_process.py` | `derived_process` |
| 热处理后硬度检查 | `post_process.py` | `detail_ops` |
| 精孔检查 | `hole_evidence.py` 或 `post_process.py` | 强证据 detail，弱证据 review |
| 首件/过程检验 | 后续 `inspection_policy.py` | review 或 detail |
| 批量/复杂件复核 | 保留风险，不默认加过多工序 | review |

禁止迁移：

- 钣金族中的 CNC/EDM/线切割泛化追加。
- 普通槽自动触发 `wire_cut_profile/edm`。
- 普通复杂度自动触发 `surface_grinding_rough`。

## 13. 实施计划

### PR1：路线输出分层与数据结构

文件：

- `backend/app/domain_v2/route_engine/assemble.py`
- `backend/app/domain_v2/route_engine/engine.py`
- `docs/contracts/process_route.schema.json`
- `backend/tests/test_api_v2_contracts.py`

内容：

- 增加 `primary_route/detail_ops/review_candidates/post_process_plan`。
- 保持 `operations` 兼容。
- 每个 op 增加 `route_effect/evidence_strength`，无法一次改 schema 时先放入 `metadata`。

验收：

- 现有测试不破。
- 前端/报价仍能读取 `operations`。

### PR2：后处理展开层

文件：

- 新增 `backend/app/domain_v2/route_engine/post_process.py`
- 修改 `engine.py` 在 assemble 后调用。
- 增加 `backend/tests/test_route_post_process.py`

内容：

- 硬铬链。
- 热处理硬度检验。
- 表处理 + 精孔/螺纹联动。

### PR3：钣金折弯/焊接证据增强

文件：

- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/tests/test_route_assertions.py`

内容：

- 折弯强/弱证据分级。
- assembly_candidate 钣金焊接强候选。
- 条件焊接文本保持 review-only。

### PR4：大板 profile 裁剪

文件：

- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/domain_v2/route_engine/skeleton.py`
- 可新增 `backend/app/domain_v2/route_engine/profiles.py`

内容：

- 钢制硬铬大板、铝长条、普通大板分型。
- `stress_relief/straightening/flatness_inspection` 按 profile 降级或保留。

### PR5：孔证据与轴类补强

文件：

- 可新增 `backend/app/domain_v2/route_engine/hole_evidence.py`
- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/process_dictionary.py`

内容：

- 孔分类。
- 外螺纹与内螺纹区分。
- 轴类长径比直线度复核。

### PR6：17 件黄金回归集

文件：

- `backend/tests/data/route_engine_snapshot_requested_20260625.json`
- `backend/tests/test_route_snapshot_requested.py`
- 可复用 `analyze_requested_routes.py` 的样件列表。

内容：

- 固化本批 17 件的期望 family、主路线和关键细项。
- 同时固化禁止项，防止 legacy 膨胀回归。

## 14. 验收标准

### 14.1 本批 17 件必须满足

钣金：

- `00083381`：有 `laser_cut_blank/bending/drilling/powder_coating`，无 CNC/EDM/线切割。
- `00083917`：有孔/攻丝，折弯至少进入复核，若规则增强后证据足够则进入 detail。
- `00083980`：无 STEP 时不崩溃；无折弯；不因 `D` 触发表处理。
- `00084158`：有折弯、焊接、喷塑。
- `00084346`：有折弯、焊接、攻丝/沉孔、喷塑小桔纹。

大板：

- `00083694/00083711`：钢制硬铬大板保留大板加工、硬铬后处理链。
- `00083722/00084089`：6061 喷砂本色氧化，去应力/校直默认不强计入 detail，进入 review 或按明确要求加入。

机加：

- `00083669`：硬质阳极后如有精孔则提示镀后孔复检。
- `00083683/00083826`：硬铬后处理链完整。
- `00083695`：喷砂 + 本色氧化同时输出。

轴类：

- `00083820/00084313`：硬铬轴类有外圆磨或镀后抛磨/尺寸复核。
- `00083835/00083857`：淬火件有硬度检验。
- `00084313`：长轴有直线度或校直复核。

### 14.2 禁止项

- 钣金族不得出现 `cnc_rough_milling/cnc_finish_milling/edm/wire_cut_profile/surface_grinding_rough`，除非人工覆盖或明确强证据且仍需复核。
- 6061 普通长条不得默认出现硬铬链、热处理链。
- 无表处理字段不得凭通用说明加表处理。
- 外螺纹不得映射为 `tapping`。
- 普通孔不得升级为精孔。

## 15. 测试策略

### 15.1 单元测试

新增：

- `test_route_post_process.py`
- `test_route_hole_evidence.py`
- `test_route_profiles.py`
- `test_route_snapshot_requested.py`

重点断言：

- 必须包含项。
- 禁止包含项。
- 弱证据进入 review 而非 detail。
- schema 兼容。

### 15.2 批量回归

固定运行：

```powershell
.\.venv\Scripts\python.exe analyze_requested_routes.py
.\.venv\Scripts\python.exe -m unittest backend.tests.test_route_snapshot_requested -v
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

### 15.3 人工抽查

每次规则调整后，抽查：

- 钣金纯平板。
- 钣金支架/护罩。
- 钢制硬铬大板。
- 6061 长条氧化件。
- 40Cr 热处理轴套。
- 长轴硬铬件。

## 16. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 迁移 legacy 细项后 V2 再次膨胀 | 所有迁移规则必须通过 family policy 和 evidence_strength；弱证据只能进 review |
| 后处理链增加报价金额 | 先通过 `detail_ops/post_process_plan` 分层输出，报价可按配置逐步启用 |
| 大板裁剪导致真实大板少算 | 钢制硬铬/高平面度仍保守；铝长条只降级去应力/校直，不删除主加工 |
| 折弯增强误伤纯平板 | 保留纯平板保护测试；折弯无强证据时进入 review 而非 detail |
| 精孔规则误报 | H7/配合孔必须看上下文，通用公差表不得触发 |
| schema 改动影响前端 | `operations` 保持兼容，新字段渐进接入 |

## 17. 推荐开发顺序

1. PR1：输出分层与 schema 兼容。
2. PR2：后处理展开层，优先硬铬和热处理。
3. PR3：钣金折弯/焊接证据增强。
4. PR4：大板 profile 裁剪。
5. PR5：孔证据、轴类长径比、外螺纹。
6. PR6：17 件黄金回归集和批量报告脚本稳定化。

不建议把所有规则一次性合入。每个 PR 都必须包含“新增能力样件”和“防误报样件”，否则很容易回到 legacy 式膨胀。
