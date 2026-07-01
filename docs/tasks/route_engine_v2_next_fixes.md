# 路线引擎 v2 第二阶段证据与上游解析修复开发文档

## 目标

在上一版已修复“非回转件误加外圆磨”“模板条件焊接直入路线”“长条大板去应力/校平”“销件孔噪声放大”的基础上，继续修复 16 件新增 PDF+STEP 验证样件暴露出的下一层问题：

- 轴类真实孔、沉孔、内螺纹和外螺纹被过度裁剪。
- 钣金骨架仍默认带 `bending`，纯平板/托板可能误加折弯。
- 钣金装配件、脚踏台类大尺寸 `assembly_candidate` 可能漏焊接。
- 复合表面处理仍按单一工序解析，漏 `clear_anodizing` 或 `powder_coating`。
- L0 标题栏存在串字段，小类也仍有大板/方件误判。

本期范围：

- `backend/app/domain_v2/route_engine/`
- `backend/app/process_recognition.py`
- `backend/app/process_dictionary.py`
- `backend/app/part_feature_builder.py`
- `backend/app/parser_service.py`
- 相关单元测试与 16 件样件快照回归

不在本期强制完成：

- 完整视觉识图
- 复杂 STEP 特征重建
- 报价系数精细化

推荐分支：`codex/route-engine-v2-next-fixes`

## 当前代码核验

对当前项目静态检查后，开发文档提到的问题基本成立：

- `backend/app/domain_v2/route_engine/skeleton.py` 中 `SHEET_METAL` 骨架仍包含 `bending`。
- `backend/app/domain_v2/route_engine/policy.py` 中 `SHEET_METAL_MATRIX["bending"]` 仍是 `REQUIRED`。
- `backend/app/domain_v2/route_engine/evidence.py::_add_hole_evidence()` 对 `family_hint == TURNING` 直接 `return`，导致轴类真实孔也被裁剪。
- `_add_surface_evidence()` 只调用单值 `surface_treatment_operation_code()`，无法同时输出 `sand_blasting + clear_anodizing`。
- `process_recognition.surface_treatment_operation_code()` 对“本色氧化，喷砂”会优先返回 `clear_anodizing` 或 `sand_blasting` 中的单个 op，缺少 plural 版本。
- `parser_service.looks_like_non_part_name()` 已有一些负例过滤，但还未覆盖“郭江峰”“调质HB220-280”“色号:PANTONE427C”“6 H7 完全贯穿”等本批复现负例。
- `part_feature_builder.build_pdf_part_category()` 当前主要按标题栏小类别名直接映射，缺少结合名称和尺寸的纠偏/复核规则。

注意：当前 L1 router 对小类置信度和几何兼容集很敏感。修复样例测试时，必须保证 fixture 的 `category_name`、`confidence`、`compatible_part_types` 与真实输入一致，否则可能先触发 `LOW_CONFIDENCE_CATEGORY_REVIEW` 或 `CATEGORY_GEOMETRY_CONFLICT_REVIEW`，导致测试没有覆盖目标问题。

## 0. 背景与问题矩阵

| 问题 | 代表件 | 当前 v2 表现 | 正确方向 |
| --- | --- | --- | --- |
| 轴类真实孔/螺纹被过度裁剪 | 84275, 84329 | TURNING 族一律删除 `drilling/tapping/counterbore` | 区分噪声孔、真实内孔、外螺纹 |
| 钣金折弯默认必经 | 83876, 84198 | 平板也有 `bending` | 折弯应由证据触发 |
| 装配/大尺寸钣金漏焊 | 84402 | `assembly_candidate` 仍可能无焊接 | assembly/multi-body 应作为焊接强证据 |
| 表处复合解析不完整 | 83695, 83710, 83722, 84089, 84115 | 漏 `clear_anodizing` / 漏 `powder_coating` | 支持多表处和颜色码推断 |
| L0 标题栏串字段/小类误判 | 多件 | 设计者、热处理、色号、孔标注进入零件名 | 标题栏字段候选增加负例过滤和置信度治理 |

## 1. 主路线目标

| 零件 | 当前问题 | 修复后期望 |
| --- | --- | --- |
| 83816 | 路线基本正确 | 保持 `turning + cylindrical_grinding + hard_chrome` |
| 83979 | 路线基本正确 | 保持 `heat_treatment + stress_relief + cylindrical_grinding + hard_chrome` |
| 84275 | 真实孔被删 | 恢复 `drilling`；必要时恢复 `counterbore/tapping`，但不得把外螺纹当 `tapping` |
| 84329 | M8/沉孔类特征被删 | 按内/外螺纹判断；外螺纹走新 op 或临时车削精加工 |
| 83679 | 机加件被抓成大板 | 修正后应走 `MACHINING`，保留 CNC 主线、孔加工、化学镍 |
| 83695/83710 | 漏本色阳极 | 输出 `sand_blasting + clear_anodizing` |
| 83866 | 大板路线基本合理 | 保持大板主线，保留硬质阳极 |
| 83694 | H7 精孔未显式体现，EDM/wire 可能过度 | 增加精孔/铰孔证据；EDM/wire 保持几何证据门控 |
| 83702 | 已基本修好 | 保持 `stress_relief + straightening` |
| 83722/84089 | 大板被抓成方件，漏本色氧化 | L0 修小类；表处补 `clear_anodizing` |
| 83876/84198 | 纯平板误加 `bending` | 无折弯证据则不加 `bending` |
| 84402 | assembly 钣金漏焊 | 输出 `bending + sheet_metal_welding + powder_coating` |
| 84115 | 色号字段未识别喷塑 | `powder_coating` 进入路线 |

## 2. P0：钣金折弯证据化

### 根因

`SHEET_METAL` 骨架和 policy 都把 `bending` 作为必经工序：

```python
SKELETONS[SHEET_METAL] = (
    "raw_material_check",
    "laser_cut_blank",
    "bending",
    "deburr",
    "inspection",
    "protective_packaging",
)
```

这会导致 83876/84198 这类 3mm 平板/托板也出现折弯。

### 修复方案

1. 从 `backend/app/domain_v2/route_engine/skeleton.py` 的 `SHEET_METAL` 骨架移除 `bending`。

```python
SHEET_METAL: (
    "raw_material_check",
    "laser_cut_blank",
    "deburr",
    "inspection",
    "protective_packaging",
)
```

2. 将 `backend/app/domain_v2/route_engine/policy.py` 中 `SHEET_METAL_MATRIX["bending"]` 从 `REQUIRED` 改为 `CONDITIONAL`。

3. 在 `evidence.py` 新增 `_add_bending_evidence(candidates, parsed, family_hint)`，只在有折弯/成形证据时添加候选。

建议证据：

- PDF/技术要求含“折弯”“折边”“折弯角”“弯曲半径”“bend”“bending”。
- STEP `part_type` 为 `formed_sheet`、`bent_sheet`、`assembly_candidate`。
- 几何高度明显不符合纯平板，例如三维高度远大于板厚。

平板保护规则：

- 83876/84198 类似 `270 x 2040 x 3`、`300 x 1700 x 3`，若无折弯文本/成形几何，不加 `bending`。
- 84402 类似 `600 x 501 x 1823` 且 `assembly_candidate`，应加 `bending`。

### 测试

新增到 `backend/tests/test_route_assertions.py`：

```python
def test_flat_sheet_metal_does_not_add_bending(self):
    route = _plan(make_part_feature(
        category_name="钣金类",
        part_type="thin_plate",
        compatible_part_types=("thin_plate", "plate"),
        bounding_box={"length": 1700, "width": 300, "height": 3},
    ))
    self.assertNotIn("bending", set(operation_codes(route)))

def test_formed_sheet_metal_adds_bending(self):
    route = _plan(make_part_feature(
        category_name="钣金类",
        part_type="assembly_candidate",
        compatible_part_types=("thin_plate", "plate", "assembly_candidate"),
        bounding_box={"length": 600, "width": 501, "height": 1823},
    ))
    self.assertIn("bending", set(operation_codes(route)))
```

实现和测试需统一 bbox 字段名。当前项目已有逻辑同时读取 `thickness` 或 `height`，新增 `_add_bending_evidence()` 也应兼容两者，例如优先 `thickness`，缺失时回退 `height`，避免测试 fixture 使用 `height` 而真实 STEP 摘要使用 `thickness` 时厚度判断失效。

## 3. P0：钣金焊接强证据补充

### 根因

上一版将条件句焊接转为 review-only，解决了纯平板误焊。但 84402 脚踏台这类 `assembly_candidate + 大尺寸 + Q235A + 喷塑` 的件，大概率需要焊接。当前只有 `fusion_type` 包含 `"assembly"` 才进几何焊接，单独 `part_type == "assembly_candidate"` 不一定触发。

### 修复方案

修改 `backend/app/domain_v2/route_engine/evidence.py::_add_welding_evidence()`：

- 将 `part_type == "assembly_candidate"` 作为强几何证据。
- 可后续加入名称证据：`脚踏台`、`支架`、`框架`、`焊接件`、`weldment`。
- 不要因为强几何证据就丢掉条件句 review-only 风险；二者可以同时存在。
- 关键实现细节：`assembly_signal` 命中后只能 `append` 焊接候选，不能 `return`。必须继续执行后面的技术要求循环，让 `WELDING_CONDITIONAL_TEXT` 仍能作为复核风险输出。

建议逻辑：

```python
assembly_signal = (
    "assembly" in fusion
    or part_type == "assembly_candidate"
)

if assembly_signal:
    candidates.append(Candidate(
        op_code="sheet_metal_welding",
        strength=GEOMETRY,
        rule_code="WELDING_ASSEMBLY_GEOMETRY",
        message="STEP/几何识别为装配或焊接候选，安排钣金焊接。",
        source=source_ref("step", rule_code="WELDING_ASSEMBLY_GEOMETRY"),
        confidence=0.72,
        requires_review=True,
        review_reason="请确认焊接位置、焊缝形式和焊后打磨。",
    ))
# 注意：这里不要 return；继续向下扫描技术要求，保留条件焊接复核风险。
```

### 验收

- 83876/84198：无 `sheet_metal_welding`，只保留 `WELDING_CONDITIONAL_TEXT` 风险。
- 84402：有 `sheet_metal_welding`，同时可保留 `WELDING_CONDITIONAL_TEXT` 复核。

## 4. P0/P1：TURNING 族真实孔与外螺纹建模

### 根因

当前 `evidence.py::_add_hole_evidence()` 中存在一刀切裁剪：

```python
if family_hint == TURNING:
    return
```

这压住了销件端面噪声孔，也同时删除了 84275/84329 上真实存在的孔、沉孔、内螺纹或外螺纹。

### 设计目标

| 情况 | 应生成 |
| --- | --- |
| 孤立端面噪声孔、外螺纹误识别 | 不生成 `drilling/tapping/counterbore` |
| 明确内螺纹孔 | `drilling + tapping` |
| 明确普通孔/横向孔/多孔结构 | `drilling`，必要时 `counterbore` |
| 外螺纹 | 不用 `tapping`；本期新增 op 或临时归入 `turning_finish` |

### 推荐新增 op

新增 `external_thread_turning`：

- 中文名：车外螺纹
- 阶段：可暂归 `turning` 或 `finish_and_precision`
- 报价归并：本期可暂归 `turning`

涉及文件：

- `backend/app/process_dictionary.py`
- `backend/app/process_recognition.py` 的 `OPERATION_STAGE_MAP`
- `backend/app/domain_v2/route_engine/policy.py`
- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/pricing_core.py` 如需报价量化

如果暂不扩工艺字典，则使用：

```python
op_code = "turning_finish"
rule_code = "EXTERNAL_THREAD_TURNING_AS_TURNING_FINISH"
```

### 规则建议

新增文本分类：

```python
EXTERNAL_THREAD_KEYWORDS = ("外螺纹", "车螺纹", "螺杆", "螺柱", "external thread")
INTERNAL_THREAD_KEYWORDS = ("螺纹孔", "攻牙", "攻丝", "盲牙", "通牙", "有效螺纹深度", "threaded hole", "tap")

def classify_thread_text(text: Any) -> str | None:
    normalized = normalize_text(text)
    if contains_any(normalized, EXTERNAL_THREAD_KEYWORDS):
        return "external"
    if contains_any(normalized, INTERNAL_THREAD_KEYWORDS):
        return "internal"
    return None
```

替换 TURNING 分支为 `_add_turning_hole_evidence()`：

- `hole_count <= 2` 且无内螺纹文本、无复杂孔型、无多直径时，按噪声孔忽略。
- `hole_count >= 3`、多孔径、`through/blind`、明确内螺纹文本时，允许 `drilling`。
- 明确内螺纹或 STEP thread hole 且没有外螺纹文本时，允许 `tapping`。
- `counterbore/countersink/reverse_counterbore` 仅在真实孔信号成立时加入。
- 外螺纹文本只产 `external_thread_turning` 或临时 `turning_finish`，不得产 `tapping`。

### 验收

- 83820：仍不出现 `drilling/counterbore/tapping`。
- 83979：不能因噪声孔恢复错误 `drilling/counterbore/tapping`。
- 84275：恢复 `drilling`；若 STEP 孔型可靠，可出现 `counterbore`。
- 84329：若 PDF/技术要求为外螺纹，不出现 `tapping`，出现 `external_thread_turning` 或临时 `turning_finish`。
- 84329 如果确认无真实孔，仅是 M8 外螺纹圆柱面被 STEP 误识别为孔，`drilling` 也应在后续 STEP 几何层面继续裁剪。本期验收先守住“不把外螺纹映射为 `tapping`”，并为 `drilling` 保留复核余地。

## 5. P1：复合表面处理解析

### 根因

当前 `surface_treatment_operation_code()` 返回单个 op，导致复合表处丢失：

- “本色氧化，喷砂”无法稳定输出 `sand_blasting + clear_anodizing`。
- “色号:PANTONE427C” 在 Q235A 钣金上下文中未推断 `powder_coating`。

### 修复方案

在 `backend/app/process_recognition.py` 新增 plural 函数：

```python
def surface_treatment_operation_codes(
    requirement: dict[str, Any],
    *,
    material: dict | None = None,
    family: str | None = None,
) -> list[str]:
    raw = normalize_text(requirement.get("raw_text"))
    standard = normalize_text(requirement.get("standard_code"))
    ops: list[str] = []

    if contains_any(raw, ("喷砂", "sandblast", "sand blasting")):
        ops.append("sand_blasting")
    if contains_any(raw, ("本色氧化", "本色阳极", "自然色氧化", "clear anodizing", "clear anodize")):
        ops.append("clear_anodizing")
    if contains_any(raw, ("硬质阳极", "硬氧", "hard anodizing", "hard anodize")):
        ops.append("hard_anodizing")
    if contains_any(raw, ("喷塑", "喷粉", "粉末喷涂", "powder", "powder coating")):
        ops.append("powder_coating")

    material_text_value = material_text(material or {})
    if (
        family == SHEET_METAL
        and contains_any(raw, ("pantone", "色号"))
        and contains_any(material_text_value, ("q235", "q235a", "spcc", "冷板"))
    ):
        ops.append("powder_coating")

    if contains_any(raw, ("镀硬铬", "hard chrome")):
        ops.append("hard_chrome")
    if contains_any(raw, ("化学镍", "chemical nickel", "化学镀镍")):
        ops.append("chemical_nickel")

    return list(dict.fromkeys(ops))
```

然后修改 `evidence.py::_add_surface_evidence()`：

- 入参需要 `parsed` 或至少需要 `material/family_hint`。
- 标题栏强证据允许多个 op 逐一追加候选。
- 技术要求正文弱证据仍保持候选/复核，不应绕过标题栏规则。

### 测试

```python
def test_clear_anodizing_and_sand_blasting_both_added(self):
    route = _plan(make_part_feature(
        category_name="方件类",
        part_type="block",
        compatible_part_types=("block",),
        material={"raw_text": "6061"},
        surface_treatment={
            "required": True,
            "raw_text": "本色氧化，喷砂",
            "standard_code": None,
            "source": {"source_type": "pdf"},
        },
    ))
    codes = set(operation_codes(route))
    self.assertIn("sand_blasting", codes)
    self.assertIn("clear_anodizing", codes)

def test_pantone_sheet_metal_q235_infers_powder_coating(self):
    route = _plan(make_part_feature(
        category_name="钣金类",
        part_type="thin_plate",
        compatible_part_types=("thin_plate", "plate"),
        material={"raw_text": "Q235A"},
        surface_treatment={
            "required": True,
            "raw_text": "色号:PANTONE427C",
            "standard_code": None,
            "source": {"source_type": "pdf"},
        },
    ))
    self.assertIn("powder_coating", set(operation_codes(route)))
```

## 6. P1：大板/机加小类纠偏

### 现象

- 83679 在机加文件夹，名称“固定板3”，抓成大板类，导致路线过度大板化。
- 83722/84089 在大板文件夹，但抓成方件类，导致漏大板路线和防变形复核。

### 修复原则

不破坏“几何不换族”的铁律。L1 仍只信业务小类，不让 STEP 几何直接换族。纠偏应在 L0 或 `build_pdf_part_category()` 阶段完成，输出更可信的小类或触发复核。

### 建议规则

在 `backend/app/part_feature_builder.py` 增强 `build_pdf_part_category()` 或新增 `refine_pdf_part_category()`：

- “固定板/安装板/连接板”如果尺寸不属于超长大板，倾向 `方件类` 或触发复核。
- “底板/推料板/背板/长板”且尺寸超长或长宽比大，倾向 `大板类` 或触发复核。
- 不直接覆盖高置信标题栏字段；中等置信时可纠偏，高置信冲突时产 `CATEGORY_REFINEMENT_REVIEW`。

建议判据：

```python
longest = dims[-1]
middle = dims[-2]
aspect = longest / max(middle, 1)

if raw_category == "大板类" and contains_any(name_text, ("固定板", "连接板", "安装板")):
    if longest < 500 and aspect < 3:
        return "方件类", 0.72, "CATEGORY_REFINED_PLATE_NAME_SIZE"

if raw_category == "方件类" and contains_any(name_text, ("底板", "推料板", "背板", "长板")):
    if longest >= 800 or aspect >= 4:
        return "大板类", 0.72, "CATEGORY_REFINED_LARGE_PLATE_SIZE"
```

### 验收

- 83679：如果尺寸约 `300 x 160 x 20` 且名称“固定板”，不应静默走大板路线并加 `straightening`。
- 83722/84089：长条板应进入 `LARGE_PLATE`，或至少触发小类纠偏复核。

## 7. P1/P2：标题栏串字段修复

### 现象

以下文本仍可能被推断为零件名：

- `郭江峰`
- `调质HB220-280`
- `色号:PANTONE427C`
- `6 H7 完全贯穿`

### 修复位置

`backend/app/parser_service.py`：

- `looks_like_non_part_name()`
- `looks_like_surface_treatment_text()`
- `infer_title_block_part_name()`
- `clean_field_value()`

### 增强负例

建议增加：

```python
# 应急兜底：只覆盖本批复现样件。根本解法不是无限加人名，
# 而是在标题栏解析时识别“设计/制图/审核/批准”等字段边界并整体排除对应单元格。
PERSON_NAME_BLACKLIST = ("郭江峰",)
HEAT_TREATMENT_TEXT_PATTERNS = (
    r"调质\s*HB\s*\d+",
    r"淬火\s*HRC\s*\d+",
)
SURFACE_COLOR_PATTERNS = (
    r"色号\s*[:：]?\s*PANTONE",
    r"PANTONE\s*\d+",
)
HOLE_CALLOUT_PATTERNS = (
    r"\d+\s*H7",
    r"完全贯穿",
    r"^\s*\d*\s*[-xX×]?\s*M\d+(?:\s*[xX×]\s*\d+(?:\.\d+)?)?\s*(深|通|螺纹|螺纹孔|攻牙|攻丝|贯穿|沉孔|盲孔)\s*\d*(?:\.\d+)?\s*$",
)
```

`M\d+` 不能单独作为非零件名判据，否则会误杀 `M8螺母座`、`M10垫片`、`销轴M6` 等合法零件名。只有当整个字段几乎只由 M 标注和孔特征词组成时，才按孔标注处理。

`looks_like_non_part_name()` 中命中以上强模式时返回 `True`。对人名黑名单要标注为短期应急；长期应优先改 `infer_title_block_part_name()` 的标题栏语义边界识别，把“设计者/审核/制图”格子的内容排除，而不是依赖具体人名。

### 测试

新增到 `backend/tests/test_pdf_part_type.py` 或 parser 相关测试：

```python
def test_designer_name_is_not_part_name(self):
    self.assertTrue(looks_like_non_part_name("郭江峰"))

def test_heat_treatment_is_not_part_name(self):
    self.assertTrue(looks_like_non_part_name("调质HB220-280"))

def test_pantone_color_is_not_part_name(self):
    self.assertTrue(looks_like_non_part_name("色号:PANTONE427C"))

def test_h7_hole_callout_is_not_part_name(self):
    self.assertTrue(looks_like_non_part_name("6 H7 完全贯穿"))

def test_thread_size_inside_real_part_name_is_allowed(self):
    self.assertFalse(looks_like_non_part_name("M8螺母座"))
    self.assertFalse(looks_like_non_part_name("M10垫片"))
    self.assertFalse(looks_like_non_part_name("销轴M6"))

def test_thread_hole_callout_is_not_part_name(self):
    self.assertTrue(looks_like_non_part_name("M8 通螺纹"))
    self.assertTrue(looks_like_non_part_name("M6深10"))
```

## 8. 测试计划

### 单元测试

优先运行：

```powershell
.\.venv\Scripts\python.exe -m unittest backend.tests.test_route_assertions -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_process_recognition -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_pdf_part_type -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_pdf_technical_requirements -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_route_snapshot -v
```

最终运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

### 16 件回归脚本

新增 `run_test_routes_batch3.py` 或扩展现有 `run_test_routes.py`，固定验证：

- 轴类：83816, 83979, 84275, 84329
- 机加：83679, 83695, 83710, 83866
- 大板：83694, 83702, 83722, 84089
- 钣金：83876, 84198, 84402, 84115

输出字段：

- PDF 名称/材料/热处理/表处/小类
- STEP `part_type/bbox/holes` summary
- legacy ops
- v2 ops
- v2 risks

### 快照验收

建议新增：

```text
backend/tests/data/route_engine_snapshot_batch3.json
```

关键断言：

- 非回转件不含 `cylindrical_grinding`。
- 纯平板钣金不含 `bending`。
- 装配钣金含 `sheet_metal_welding`。
- 84115 含 `powder_coating`。
- 83695/83710/83722/84089 含 `clear_anodizing`。
- 83820/83979 不因外螺纹或噪声孔误加 `tapping`。
- 84275 含 `drilling`。

## 9. 分批实施建议

### PR1：钣金折弯 + 焊接强证据

文件：

- `backend/app/domain_v2/route_engine/skeleton.py`
- `backend/app/domain_v2/route_engine/policy.py`
- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/tests/test_route_assertions.py`

验收：

- 83876/84198 无 `bending`。
- 84402 有 `bending + sheet_metal_welding`。
- 纯模板焊接仍 review-only。

### PR2：TURNING 真实孔/外螺纹

文件：

- `backend/app/process_dictionary.py`，如新增 `external_thread_turning`
- `backend/app/process_recognition.py`
- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/domain_v2/route_engine/policy.py`
- `backend/tests/test_route_assertions.py`

验收：

- 84275 恢复真实孔。
- 84329 不把外螺纹当 `tapping`。
- 83820/83979 不回归噪声孔污染。

### PR3：复合表处

文件：

- `backend/app/process_recognition.py`
- `backend/app/domain_v2/route_engine/evidence.py`
- `backend/app/part_feature_builder.py`
- 相关测试

验收：

- “本色氧化，喷砂”输出 `sand_blasting + clear_anodizing`。
- `PANTONE + Q235A + 钣金` 输出 `powder_coating`。
- 空白/孤立 `D` 不触发表处。

### PR4：L0 标题栏/小类修复

文件：

- `backend/app/parser_service.py`
- `backend/app/part_feature_builder.py`
- `backend/tests/test_pdf_part_type.py`
- `backend/tests/test_pdf_technical_requirements.py`

验收：

- `郭江峰` 不再作为零件名。
- `调质HB220-280` 不再作为零件名。
- `色号:PANTONE427C` 不再作为零件名。
- `6 H7 完全贯穿` 不再作为零件名。
- 83722/84089 小类向大板纠偏或触发强复核。

## 10. 风险与回滚

| 风险 | 缓解 |
| --- | --- |
| 移除钣金骨架 `bending` 导致真实折弯件漏折弯 | 增加 `assembly_candidate`、bbox 高度、折弯关键词证据；保留复核 |
| TURNING 真实孔恢复后，销件噪声孔回归 | 用 `hole_count/diameter_set/thread_text` 分级，并保留 83820 守门测试 |
| 新增 `external_thread_turning` 影响报价 | 可先报价归并到 `turning`，后续再细化报价系数 |
| PANTONE 推断喷塑误判 | 限定 `family=SHEET_METAL + Q235/SPCC/冷板`，铝件不使用该推断 |
| 小类纠偏过度 | 不直接覆盖高置信小类；先用中等置信纠偏和 `CATEGORY_REFINEMENT_REVIEW` |

## 11. 最终验收标准

- 16 件全部路线不超过 18 道，无旧链式膨胀。
- 非回转件无 `cylindrical_grinding`。
- 纯平板钣金无 `bending/sheet_metal_welding`。
- 组装钣金 84402 有 `bending/sheet_metal_welding/powder_coating`。
- 轴类 83816/83979 不被孔噪声污染。
- 84275 有真实孔加工。
- 84329 外螺纹不映射为 `tapping`。
- “本色氧化，喷砂”同时有 `clear_anodizing + sand_blasting`。
- PANTONE427C 钣金件有 `powder_coating`。
- 设计者、热处理、色号、孔标注不再串入 `part_name`。
- 大板/方件误抓至少进入复核，不静默走错族。
