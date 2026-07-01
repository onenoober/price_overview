# 路线引擎 v2 证据精度修复开发方案（焊接/表处/轴铣/外螺纹）

> 面向 16 件新验证样件暴露的 4 个证据层问题。**目标：从根因解决，且不引入新偏差。**
> 贯穿原则：① 模板/噪声文本不得证明工序；② 几何是二级特征，单独不得产工序，只能产复核；
> ③ 任何"提级为必做"的规则必须让位于"条件句/弱来源"判定；④ 每个修复都配最小守门测试 +
> 反例测试（防止把该触发的也误杀）。

涉及文件：
- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/process_recognition.py`（`surface_treatment_operation_codes`）
- `backend/tests/test_route_assertions.py`

不在本期：标题栏字段边界（投影串名）、跨族小类纠偏（方件→钣金/圆件）——属 L0/L1，另案。

---

## 问题与根因总览

| # | 问题 | 代表件 | 根因（已定位） | 严重度 |
|---|---|---|---|---|
| 1 | 单片钣金被强加 `sheet_metal_welding` | 83504、84333 | `_has_explicit_welding_action()` 在含"进行/焊后打磨"时把**条件句模板**提级为 required，绕过条件句保护 | 🔴 高（回归） |
| 2 | "亮光白色（9003）"漏 `powder_coating` | 83712、83945 | `surface_treatment_operation_codes()` 只认带"喷塑"字样或 PANTONE；RAL/中文颜色名落空 | 🟠 中 |
| 3 | 光轴误加 `shaft_milling` | 83979 | `_is_complex_shaft_surface()` 把 STEP 噪声类 `complex_surface_candidate` 当真实铣削特征 | 🟡 低 |
| 4 | 轴端 M12 外螺纹漏 `external_thread_turning` | 83727 | 外螺纹仅靠"外螺纹"文本触发；无文本的 `M\d+` 外圆螺纹不识别 | 🟡 低 |

---

## P1（最高优先）· 焊接模板条件句不得提级为必焊

### 根因

`evidence.py::_add_welding_evidence()` 文本分支：

```python
kind = _classify_sentence(raw)
if _has_explicit_welding_action(raw):     # ← 病灶：无条件覆盖
    kind = "required"
elif pending_conditional and kind == "required":
    kind = "conditional"
```

几乎所有图纸的标准模板第 3 条：
*"**对于尺寸较大的**钣金件，对接合处**进行**焊接加固，**焊后打磨**"*
本应被 `_classify_sentence` 判为 `conditional`（句首"对于…的钣金件"），但因含"进行/焊后打磨"被
`_has_explicit_welding_action()` 强行提级为 `required` → 单片件（83504 折弯支架、84333 单片平板）
被加焊接。

### 修复设计（根因 + 不误杀）

**铁律：条件句/弱来源永远优先；`_has_explicit_welding_action` 只能"抢救"被误判为 instructional 的
真实焊接句，绝不能覆盖 conditional。**

```python
kind = _classify_sentence(raw)
# 条件句优先（模板"对于尺寸较大的钣金件…"恒为条件句 → review-only）
if pending_conditional and kind == "required":
    kind = "conditional"
# 仅当不是条件句时，才允许用显式动作把 instructional 抢救成 required
if kind == "instructional" and _has_explicit_welding_action(raw):
    kind = "required"
```

要点：
- 删除"无条件 `if _has_explicit_welding_action: kind=required`"。
- 真正无条件的焊接句（"对接处满焊，焊缝高度 2mm"）本就被 `_classify_sentence` 判 `required`，不依赖该函数，**不受影响**。
- 装配/焊接件仍由 `assembly_signal`（fusion 含 assembly 或 `part_type==assembly_candidate`）走几何强证据，**与文本分支解耦、不受影响**（83712/83945 仍正确焊接）。
- 模板条件句 → `WELDING_CONDITIONAL_TEXT` 复核（review-only），不入路线。

### 不引入新问题的保证

- 几何装配证据独立，weldment 仍焊接（反例件 83712/83945 守门）。
- 真实无条件焊接句仍 required（反例守门）。
- 仅"被条件标记命中的焊接句"行为变化，且方向是更保守（改加为复核），不会漏掉应焊但**必有几何或无条件文本佐证**的件。

### 守门测试（test_route_assertions.py 增补）

```python
def test_template_conditional_welding_not_added_on_single_sheet(self):
    # 标准模板 + 单片钣金（thin_plate，非装配） → 不焊，只复核
    route = _plan(make_part_feature(
        category_name="钣金类", part_type="thin_plate",
        compatible_part_types=("thin_plate","plate"),
        bounding_box={"length":650,"width":275,"height":3},
        technical_requirements=[{"raw_text":"对于尺寸较大的钣金件,对接合处进行焊接加固,焊后打磨"}],
    ))
    self.assertNotIn("sheet_metal_welding", set(operation_codes(route)))
    self.assertIn("WELDING_CONDITIONAL_TEXT", risk_codes(route))

def test_assembly_weldment_still_welds_with_same_template(self):
    route = _plan(make_part_feature(
        category_name="焊接类", part_type="assembly_candidate",
        compatible_part_types=("thin_plate","plate","assembly_candidate"),
        technical_requirements=[{"raw_text":"对于尺寸较大的钣金件,对接合处进行焊接加固,焊后打磨"}],
    ))
    self.assertIn("sheet_metal_welding", set(operation_codes(route)))

def test_unconditional_weld_text_still_required(self):
    route = _plan(make_part_feature(
        category_name="钣金类", part_type="thin_plate",
        compatible_part_types=("thin_plate","plate"),
        technical_requirements=[{"raw_text":"对接处满焊,焊缝高度2mm,焊后打磨"}],
    ))
    self.assertIn("sheet_metal_welding", set(operation_codes(route)))
```

---

## P2 · 表处颜色名（RAL/中文）推断喷塑

### 根因

`process_recognition.surface_treatment_operation_codes()` 喷塑分支需要"喷塑/喷粉/喷涂/powder"字样；
`亮光白色（9003）`（RAL 9003 亮光白）无"喷塑"二字 → 不命中 → 漏 `powder_coating`。

### 修复设计（只在强来源 + 钢/钣金上下文）

新增颜色名 → 喷塑推断，**严格门控避免误判为阳极色或装饰文字**：

```python
RAL_PATTERN = r"\bral\s?\d{4}\b"          # RAL7035/RAL9003
COLOR_PAINT_NAMES = ("亮光白","亮白","哑光白","哑光黑","亮光黑","亮光","哑光","半光")
PAINT_COLOR_CODE = r"\(?\s*\d{4}\s*\)?"   # （9003）

def _looks_like_paint_color(raw: str) -> bool:
    return (
        re.search(RAL_PATTERN, raw) is not None
        or any(name in raw for name in COLOR_PAINT_NAMES)
    )
```

在喷塑分支后补：

```python
# 颜色名/RAL 推断喷塑：仅当 ① 表处来自标题栏字段(强来源) ② 材料为碳钢/钣金 ③ 非铝(铝走阳极)
material_text_value = material_text(material or {})
is_aluminum = contains_any(material_text_value, ("6061","6063","5052","7075","铝","al-"))
steel_or_sheet = (
    family == "SHEET_METAL"
    or contains_any(material_text_value, ("q235","q345","spcc","冷板","碳钢","45#","45钢"))
)
if (
    "powder_coating" not in ops and "powder_coating_texture" not in ops
    and "white_powder_coating" not in ops
    and _looks_like_paint_color(raw)
    and steel_or_sheet and not is_aluminum
):
    ops.append("powder_coating")
```

> 调用侧 `_add_surface_evidence` 已传 `material=parsed.material, family=family_hint`，无需改签名。
> **只对标题栏强来源生效**：弱来源（tech_text）路径仍走 `SURFACE_TREATMENT_UNVERIFIED` 候选，不会因正文出现颜色词乱加。

### 不引入新问题的保证

- 铝件颜色 → 不推喷塑（继续走 color_anodizing/clear_anodizing），避免"铝件被喷塑"。
- 不锈钢/未知材料 + 非钣金 → 不推（保守）。
- 仅标题栏表处字段触发，正文颜色描述不触发。

### 守门测试

```python
def test_ral_white_on_sheet_steel_infers_powder_coating(self):
    route = _plan(make_part_feature(
        category_name="钣金类", part_type="assembly_candidate",
        compatible_part_types=("thin_plate","plate","assembly_candidate"),
        material={"raw_text":"Q235A"},
        surface_treatment={"required":True,"raw_text":"亮光白色（9003）",
                           "standard_code":None,"source":{"source_type":"pdf","file_id":"pdf-1"}},
    ))
    self.assertIn("powder_coating", set(operation_codes(route)))

def test_color_text_on_aluminum_does_not_powder_coat(self):
    route = _plan(make_part_feature(
        category_name="方件类", part_type="block", compatible_part_types=("block",),
        material={"raw_text":"6061"},
        surface_treatment={"required":True,"raw_text":"本色氧化，喷砂",
                           "standard_code":None,"source":{"source_type":"pdf","file_id":"pdf-1"}},
    ))
    codes = set(operation_codes(route))
    self.assertIn("clear_anodizing", codes)
    self.assertNotIn("powder_coating", codes)
```

---

## P3 · `shaft_milling` 不得由 STEP 噪声类单独触发

### 根因

`_is_complex_shaft_surface()` 返回 True 的条件含 `part_type == "complex_surface_candidate"`，而该 part_type
是 STEP 对细长轴的**噪声分类**（83979 光轴即为此类）。于是无任何铣削特征的光轴被加 `shaft_milling`。

### 修复设计（几何噪声只产复核，真实特征才产工序）

1. **`shaft_milling` 触发改为只认真实铣削特征证据**：flat/keyway/obround 文本或 `flat_count/keyway_count/slot_count`
   特征计数；**移除 `complex_surface_candidate` 作为触发**。
2. 径向/横向孔走 `cross_drilling`（已有），其判据用**侧孔几何**(`is_side_hole`) 或横孔文本，而非 part_type。
3. `complex_surface_candidate` 仅产 **`SHAFT_SURFACE_REVIEW`**（review-only，不入路线），把"几何怀疑"交人工。

```python
# _is_complex_shaft_surface：删除 part_type==complex_surface_candidate 分支，仅保留高复杂度分数
return shaft_like and score >= 70           # 不再吃 complex_surface_candidate

# _add_shaft_milling_evidence：complex_surface_candidate → 仅复核
if (parsed.geometry_part_type == "complex_surface_candidate"
        and not (has_flat or has_obround or has_keyway or has_cross)):
    # 不产工序，仅提示几何复核（通过 review_only 候选实现）
    candidates.append(Candidate(
        op_code="shaft_milling", strength=GEOMETRY, rule_code="SHAFT_SURFACE_REVIEW",
        message="STEP 识别为复杂回转面但无明确铣削特征，提示复核，不入路线。",
        source=source_ref("step", rule_code="SHAFT_SURFACE_REVIEW"),
        confidence=0.3, requires_review=True,
        review_reason="确认是否真有铣扁/键槽/横孔等铣削特征。",
        review_code="SHAFT_SURFACE_REVIEW", review_only=True))
```

### 不引入新问题的保证

- 83824 动力轴（真实径向孔）：径向孔经 `_add_turning_hole_evidence` 仍产 `drilling`，横孔/铣特征经文本或
  侧孔几何产 `cross_drilling`/`shaft_milling`——**有真实证据仍触发**。需在守门测试里用"含横孔/铣扁证据"的 fixture 固化。
- 83979 光轴：无铣特征 → 不加 `shaft_milling`，只 `SHAFT_SURFACE_REVIEW`。
- 真正复杂的轴仍可由复杂度分数 ≥70 或显式特征触发，不会一刀切漏掉。

### 守门测试

```python
def test_plain_shaft_no_shaft_milling(self):
    route = _plan(make_part_feature(
        category_name="圆件类", part_type="complex_surface_candidate",
        compatible_part_types=("shaft",),
        bounding_box={"length":122,"width":8,"height":8},
        holes=[{"count":2,"hole_type":"thread","thread_size":"M3"}],
        technical_requirements=[{"raw_text":"端面螺纹孔M3攻牙"}],
    ))
    self.assertNotIn("shaft_milling", set(operation_codes(route)))

def test_shaft_with_flat_keeps_shaft_milling(self):
    route = _plan(make_part_feature(
        category_name="圆件类", part_type="shaft", compatible_part_types=("shaft",),
        technical_requirements=[{"raw_text":"轴端铣两面对称扁,宽12"}],
    ))
    self.assertIn("shaft_milling", set(operation_codes(route)))
```

---

## P4 · 轴端外螺纹无文本时的几何识别

### 根因

`_add_turning_hole_evidence()` 仅在 `classify_thread_text` 命中"外螺纹/车螺纹/螺杆…"文本时产
`external_thread_turning`。83727 的 `M12` 外圆螺纹只有标注无"外螺纹"字样 → 漏。

### 修复设计（保守、只产复核候选，绝不误攻牙）

新增**几何/标注**外螺纹判据，并保持"外螺纹绝不映射 tapping"的已有铁律：

```python
def _has_external_thread_geometry(holes, requirements, bbox) -> bool:
    """螺纹特征位于外圆(直径≈零件最大外径)、且不存在对应内孔 → 判外螺纹。"""
    max_od = max([numeric_value(bbox.get(k)) or 0 for k in ("length","width","height")] or [0])
    for hole in holes:
        if not (is_thread_hole(hole) or str(hole.get("hole_type")) in {"thread","thread_candidate"}):
            continue
        d = numeric_value(hole.get("diameter")) or 0
        # 螺纹"孔"直径接近外圆最小截面（轴径量级），且无明显内腔 → 大概率外螺纹
        if d and _diameter_matches_outer_step(d, holes, bbox):
            return True
    return False
```

触发后：
- 产 `external_thread_turning`（**review_only/低置信**，requires_review=True），不直接占主路线但出现在候选/复核。
- 该螺纹特征**从内螺纹/攻牙判定中排除**（已有 `has_external_text` 排除逻辑扩展为 `has_external_text or external_geom`）。

> P4 风险最高（几何易误判），故**只产复核候选**，宁可标复核也不静默加错。真实内螺纹（83824/83727 的 M4）
> 仍正常 `tapping`。

### 不引入新问题的保证

- 外螺纹几何判据**只产复核候选**，不进主路线 → 即使误判也只是多一条复核，不污染报价主路线。
- 内螺纹 tapping 路径仅在"非外螺纹"时触发，扩展排除条件后**更不会把外螺纹当攻牙**。
- 无螺纹特征的件完全不受影响。

### 守门测试

```python
def test_external_thread_geometry_adds_turning_not_tapping(self):
    route = _plan(make_part_feature(
        category_name="圆件类", part_type="shaft", compatible_part_types=("shaft",),
        bounding_box={"length":135,"width":12,"height":12},
        holes=[{"count":1,"hole_type":"thread","diameter":12},   # M12 外圆螺纹
               {"count":1,"hole_type":"thread","diameter":3.3,"thread_size":"M4"}],  # M4 内孔
        technical_requirements=[{"raw_text":"端面M4-6H深8"}],
    ))
    codes = set(operation_codes(route))
    self.assertIn("external_thread_turning", codes)
    self.assertIn("tapping", codes)   # M4 内孔仍攻牙
```

---

## 实施顺序与回归基线

1. **P1 焊接**（最高，修回归）→ 跑 `test_route_assertions` + 16 件回归确认 83504/84333 不再焊接、83712/83945 仍焊接。
2. **P2 表处** → 确认 83712/83945 出 `powder_coating`、铝件不误喷塑。
3. **P3 轴铣** → 确认 83979 无 `shaft_milling`、83824 仍有铣/孔特征。
4. **P4 外螺纹** → 确认 83727 出 `external_thread_turning` 候选、不误攻牙。

每步独立可上线、可回滚。每步后：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests
.\.venv\Scripts\python.exe run_batch_check.py    # 16 件人工核对 diff
```

并更新 `backend/tests/data/route_engine_snapshot*.json` 快照基线（仅当 diff 全部可解释为本方案预期改动时）。

## 全局"不引入新问题"约束（验收门）

- 既有 `test_route_assertions` / `test_route_engine_policy` / `test_process_recognition` / `test_route_snapshot` **全绿**。
- 新增行为全部"加保守、减激进"：P1/P3 把误加改复核，P2 仅强来源+钢件加，P4 只产复核候选。
- 任一修复都配 **正例（应触发仍触发）+ 反例（不应触发不触发）** 双向守门，杜绝"修一个漏一个"。
