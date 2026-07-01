# 表面处理计价根治开发文档

## 1. 目标和边界

本文只针对表面处理费用计算，不改动材料费、普通加工费、管理费、税金的既有公式入口。

目标是把当前“所有表面处理几乎统一按 STEP 表面积 m2 计价”的实现，改造成“按表处类型选择计价基准”的可配置规则引擎。

目标总公式保持为：

```text
表面处理费用 = 表面处理类型对应的计价基准数量 * 对应单价
```

其中“计价基准数量”不固定，可以是：

- `area_m2`：表面积，单位 m2。
- `net_weight_kg`：净重，单位 kg。
- `gross_weight_kg`：毛重，单位 kg，净重缺失时可作为复核 fallback。
- `piece_count`：件数。
- `lot`：批次/最低起步价。

## 2. 当前问题

当前代码位置：

- `backend/app/pricing_core.py`
- `calculate_surface_treatment_area()`
- `SURFACE_TREATMENT_STANDARD_PRICE_RULES`
- `build_quantity_result()` 中表处工程量生成逻辑
- `build_quote_result()` 中表处费用生成逻辑

当前主流程对所有表处工序执行：

```python
surface_quantity = calculate_surface_treatment_area(geometry)
```

随后使用 `SURFACE_TREATMENT_STANDARD_PRICE_RULES[surface_operation]` 中的 m2 单价计算：

```text
amount = max(surface_area_m2 * unit_price_per_m2, minimum_charge)
```

这会导致两个问题：

1. 需要按重量、件数或批次计价的表处，被错误套用了面积口径。
2. 代码里虽然已有 `calculate_surface_treatment_weight()`，但当前表处主流程没有调用它，净重没有进入表处报价链路。

## 3. 为什么不同表处需要不同计价基准

表面处理成本由供应商工艺、装挂方式、处理槽/炉批次、膜厚、遮蔽、良率和检测要求决定，不存在所有表处统一按净重或统一按面积的稳定规则。

公开资料和行业实践显示：

- 阳极氧化常与表面积、膜厚、电流密度相关。CHEMEON 的 720 Rule 说明阳极氧化用每平方英尺面积的安培分钟来描述膜厚形成关系；多个阳极氧化估算器也以表面积和单位面积费率作为核心输入。
- 喷粉/喷塑的粉末用量按覆盖面积、膜厚、粉末比重和转移效率估算。IFS Coatings 的粉末用量计算器要求输入总表面积，Reliant Finishing Systems 也给出按表面积计算涂粉成本的示例。
- 发黑/黑氧化这类批量化学处理，公开资料中常见按重量或批次最低收费。Birchwood Technologies 和 Gear Solutions 均提到黑氧化运营成本可按 finished work 的每磅成本描述；Santa Clara Plating 的 black oxide 价目表体现最低收费和最大重量约束。

因此，表处类型对应计价基准应来自以下优先级：

1. **内部供应商报价/历史订单**：最优先。直接记录供应商报价单中的单位，例如 CNY/m2、CNY/kg、CNY/pcs、CNY/lot。
2. **公司核价规则/采购约定**：如果内部已经约定某供应商某表处按 kg 或 m2，则作为主数据规则。
3. **行业默认规则**：没有历史报价时使用默认规则，但必须标记 `requires_review=true`。
4. **人工复核覆盖**：报价员可在 UI 中修改计价基准、单价、最低收费和备注。

## 4. 表处类型默认计价基准建议

以下默认规则只作为 first-pass，最终应以本公司供应商报价主数据为准。

| 表处类型 | 建议计价基准 | 原因 | 默认复核 |
|---|---|---|---|
| `clear_anodizing` 本色阳极 | `area_m2` | 膜厚和电化学处理与外露面积强相关 | 是 |
| `hard_anodizing` 硬质阳极 | `area_m2` | 膜厚、电流和处理面积强相关 | 是 |
| `color_anodizing` 彩色/黑色阳极 | `area_m2` | 面积、颜色、封闭和外观要求影响大 | 是 |
| `sand_blasting` 喷砂 | `area_m2` | 处理时间和磨料消耗与外露面积相关 | 是 |
| `powder_coating` 喷粉/喷塑 | `area_m2` | 粉末覆盖率按面积、膜厚、比重估算 | 是 |
| `white_powder_coating` 白色喷塑 | `area_m2` | 同喷粉，颜色可能影响单价 | 是 |
| `powder_coating_texture` 纹理喷塑 | `area_m2` | 同喷粉，纹理粉可能更高单价 | 是 |
| `chemical_nickel` 化学镍 | `area_m2` 或 `net_weight_kg` | 取决于供应商；精密件常按面积/最低收费，小件批量可能按 kg | 是 |
| `hard_chrome` 镀硬铬 | `area_m2` 或 `net_weight_kg` | 膜厚、遮蔽、后抛/后磨影响大；供应商口径差异大 | 是 |
| `black_oxide` 发黑/黑氧化 | `net_weight_kg` 或 `lot` | 批量化学处理，常见 kg/批次最低收费 | 是 |
| `phosphating` 磷化 | `net_weight_kg` 或 `area_m2` | 批量件常按 kg，大片/外观件可按面积 | 是 |
| `passivation` 钝化 | `net_weight_kg` 或 `lot` | 小件批量处理常按 kg/批次 | 是 |
| 未识别表处 | `lot` | 无可靠基准，使用最低起步价并强制复核 | 是 |

关键点：不要把 `chemical_nickel`、`hard_chrome` 固定死。它们必须支持供应商级规则覆盖，因为在真实报价里既可能按面积，也可能按重量/批次。

## 5. 数据模型设计

新增表处计价规则对象，不替换现有普通加工规则。

建议在 `backend/app/pricing_core.py` 或后续独立模块 `backend/app/surface_treatment_pricing.py` 中定义：

```python
@dataclass(frozen=True)
class SurfaceTreatmentPriceRule:
    operation_code: str
    pricing_basis: str  # area_m2 | net_weight_kg | gross_weight_kg | piece_count | lot
    unit_price: float
    unit: str           # CNY/m2 | CNY/kg | CNY/pcs | CNY/lot
    minimum_charge: float
    source_id: str
    rule_id: str
    version: str
    requires_review: bool = True
    fallback_allowed: bool = True
    notes: str = ""
```

主数据建议字段：

```json
{
  "operation_code": "chemical_nickel",
  "supplier_id": "default",
  "material_family": "steel",
  "pricing_basis": "area_m2",
  "unit_price": 900,
  "unit": "CNY/m2",
  "minimum_charge": 80,
  "priority": 100,
  "effective_from": "2026-01-01",
  "source_type": "supplier_quote|internal_rule|industry_default",
  "requires_review": true
}
```

## 6. 表处计价基准如何得到

### 6.1 从供应商报价中得到

供应商报价单是最高优先级。解析报价单或人工录入时，提取：

- 表处名称：如化学镍、硬质阳极、镀硬铬。
- 单位：元/m2、元/kg、元/件、元/批。
- 单价。
- 最低收费。
- 适用材料：铝、钢、不锈钢等。
- 特殊条件：膜厚、颜色、遮蔽、盐雾、后处理。

如果报价单写的是：

```text
硬质阳极：220 元/m2，最低 80 元
```

则：

```json
{
  "operation_code": "hard_anodizing",
  "pricing_basis": "area_m2",
  "unit_price": 220,
  "minimum_charge": 80
}
```

如果报价单写的是：

```text
发黑：6 元/kg，最低 50 元
```

则：

```json
{
  "operation_code": "black_oxide",
  "pricing_basis": "net_weight_kg",
  "unit_price": 6,
  "minimum_charge": 50
}
```

### 6.2 从历史订单反推

当历史报价有表处金额和工程量时，可以反推单位：

- 如果金额与表面积相关性更高，候选 `area_m2`。
- 如果金额与重量相关性更高，候选 `net_weight_kg`。
- 如果同一批次金额基本固定，候选 `lot`。
- 如果金额随数量线性变化，候选 `piece_count`。

反推结果不能直接静默生效，应进入“候选规则”，由报价负责人确认后转为正式规则。

### 6.3 从行业默认规则得到

当供应商和历史数据都缺失时，使用行业默认基准：

- 阳极、喷粉、喷砂：优先 `area_m2`。
- 发黑、钝化、磷化：优先 `net_weight_kg` 或 `lot`。
- 化学镍、镀硬铬：默认 `area_m2`，但强制复核并允许供应商规则覆盖。

这些默认规则来自工艺成本结构和公开资料：阳极/喷粉/喷砂主要受处理面积影响；发黑/批量化学处理常按重量或批次管理；化学镍和硬铬受膜厚、遮蔽、面积、批次影响，供应商口径差异更大。

## 7. 工程量来源设计

### 7.1 表面积 `area_m2`

来源优先级：

1. STEP 解析得到的 `geometry.surface_area`。
2. 如果 STEP 表面积缺失，用 bbox 估算外包络表面积，并标记复核。
3. 如果连 bbox 都缺失，则无法自动报价，生成 `MISSING_SURFACE_TREATMENT_QUANTITY` 风险。

### 7.2 净重 `net_weight_kg`

来源优先级：

1. STEP `net_weight`，如果 STEP 文件包含实体体积和材料密度，或解析器能给出净重。
2. PDF 图纸重量字段，如“重量/单重/Weight”。
3. STEP 体积 * 材料密度估算净重。
4. 如果净重缺失，但毛重可得，允许 fallback 到毛重，并标记 `SURFACE_NET_WEIGHT_FALLBACK_TO_GROSS_WEIGHT`。

### 7.3 毛重 `gross_weight_kg`

来源：

```text
bounding_box.length * width * height * material_density
```

注意：毛重适合材料费，不一定适合表处费。只有规则明确允许 fallback 时，表处才可使用毛重。

### 7.4 件数 `piece_count`

来源：

- `part.quantity`
- 如果缺失，按 1 件 first-pass，并标记复核。

### 7.5 批次 `lot`

来源：

- 默认 1 lot。
- 用于最低收费、无法识别口径或供应商按批报价。

## 8. 计算流程设计

新增函数：

```python
def resolve_surface_treatment_rule(
    operation_code: str,
    *,
    material: dict[str, Any],
    supplier_id: str | None = None,
    region: str = "south_china",
) -> SurfaceTreatmentPriceRule:
    ...
```

新增工程量函数：

```python
def calculate_surface_treatment_quantity(
    *,
    pricing_basis: str,
    geometry: dict[str, Any],
    material: dict[str, Any],
    part_quantity: float | None,
    gross_weight: dict[str, Any],
    measured_weight_value: float | None,
    measured_weight_unit: str,
    measured_weight_source: dict[str, Any],
) -> dict[str, Any]:
    ...
```

报价公式：

```python
quantity = calculate_surface_treatment_quantity(rule.pricing_basis, ...)
amount = max(quantity.value * rule.unit_price, rule.minimum_charge)
```

quote item 中必须记录：

- `operation_code`
- `quantity`
- `unit`
- `unit_price`
- `amount`
- `formula`
- `pricing_basis`
- `requires_review`
- `price_source`
- `basis`

示例：

```json
{
  "item_type": "surface_treatment",
  "operation_code": "black_oxide",
  "pricing_basis": "net_weight_kg",
  "quantity": 2.56,
  "unit": "kg",
  "unit_price": 6,
  "amount": 50,
  "formula": "max(net_weight_kg * 6 CNY/kg, minimum_charge 50 CNY)"
}
```

## 9. 当前代码修改点

### 9.1 不要继续在表处主流程中固定调用面积

当前：

```python
surface_quantity = calculate_surface_treatment_area(geometry)
```

改为：

```python
rule = resolve_surface_treatment_rule(surface_operation, material=material)
surface_quantity = calculate_surface_treatment_quantity(
    pricing_basis=rule.pricing_basis,
    geometry=geometry,
    material=material,
    part_quantity=part_quantity,
    gross_weight=gross_weight,
    measured_weight_value=measured_weight_value,
    measured_weight_unit=measured_weight_unit,
    measured_weight_source=measured_weight_source,
)
```

### 9.2 保留旧面积函数

`calculate_surface_treatment_area()` 不删除，作为 `pricing_basis == "area_m2"` 的实现。

### 9.3 启用现有重量函数

`calculate_surface_treatment_weight()` 可以作为 `net_weight_kg` 的实现基础，但需要确认它的优先级：

```text
STEP net weight -> PDF weight -> STEP volume*density -> gross fallback
```

### 9.4 表处规则表改为多单位

当前 `SURFACE_TREATMENT_STANDARD_PRICE_RULES` 都是 `m2`。需要拆成新的规则表，例如：

```python
SURFACE_TREATMENT_PRICING_RULES = {
    "hard_anodizing": SurfaceTreatmentPriceRule(
        operation_code="hard_anodizing",
        pricing_basis="area_m2",
        unit_price=220.0,
        unit="CNY/m2",
        minimum_charge=80.0,
        ...
    ),
    "black_oxide": SurfaceTreatmentPriceRule(
        operation_code="black_oxide",
        pricing_basis="net_weight_kg",
        unit_price=6.0,
        unit="CNY/kg",
        minimum_charge=50.0,
        ...
    ),
}
```

## 10. 风险码设计

新增或调整风险码：

| 风险码 | 触发条件 |
|---|---|
| `SURFACE_PRICING_BASIS_DEFAULT_REVIEW` | 使用行业默认计价基准 |
| `SURFACE_PRICING_BASIS_SUPPLIER_MISSING` | 无供应商规则 |
| `SURFACE_NET_WEIGHT_MISSING` | 表处规则要求净重但无法取得 |
| `SURFACE_NET_WEIGHT_FALLBACK_TO_GROSS_WEIGHT` | 净重缺失，使用毛重 fallback |
| `SURFACE_AREA_FALLBACK_FROM_BBOX` | 表面积缺失，用 bbox 估算 |
| `SURFACE_MINIMUM_CHARGE_APPLIED` | 启用最低收费 |
| `SURFACE_PRICING_UNIT_CHANGED_FROM_LEGACY` | 新规则与旧 m2 规则不同，用于迁移期审计 |

## 11. 测试计划

### 11.1 单元测试

新增测试文件：

```text
backend/tests/test_surface_treatment_pricing_basis.py
```

覆盖：

- 阳极氧化使用 `area_m2`。
- 喷塑使用 `area_m2`。
- 发黑使用 `net_weight_kg`。
- 化学镍默认 `area_m2`，供应商规则可覆盖为 `net_weight_kg`。
- 镀硬铬默认 `area_m2`，供应商规则可覆盖。
- 净重缺失时按规则 fallback 到毛重，并生成风险。
- 最低收费正确生效。
- 税金仍按 `(加工费 + 表处费 + 管理费) * 13%`，不改变税金模块。

### 11.2 回归测试

用当前 32 套 PDF/STEP 重新跑：

- 输出每件表处 `pricing_basis`。
- 输出新旧表处费用差异。
- 确认材料费、加工费、管理费、税金入口没有被改动。
- 对于没有表处的件，报价不应变化。

### 11.3 验收标准

- quote item 中每条表处费用都能看到 `pricing_basis`。
- 表处费用不再统一使用 m2。
- 规则表可配置不同单位。
- 供应商报价可覆盖行业默认规则。
- 任何 fallback 都有风险码。
- 现有材料费、加工费、管理费、税金公式不被重构。

## 12. 迁移策略

第一阶段：兼容审计

- 保留旧 m2 计算。
- 新增新规则计算。
- 同时报出 `legacy_surface_amount` 和 `new_surface_amount`。
- 不直接影响正式报价，只输出差异。

第二阶段：灰度启用

- 对规则明确的表处启用新引擎。
- 对 `chemical_nickel`、`hard_chrome` 等供应商口径不稳定的表处继续强制复核。

第三阶段：正式替换

- 表处报价统一走新规则。
- 旧 m2 表统一降级为 `area_m2` 类型规则，而不是硬编码逻辑。

## 13. 资料来源和基准来源说明

表处类型的默认计价基准不是凭空设定，而是按以下方式得到：

1. 查看当前代码和实际输出，确认系统正在按 STEP 表面积 m2 计价。
2. 结合表处工艺成本结构判断：膜厚/涂层覆盖/喷涂类通常与面积强相关；批量化学处理和发黑类可按重量或批次管理。
3. 参考公开资料：
   - CHEMEON 720 Rule calculator：阳极氧化膜厚与每平方英尺面积的安培分钟相关。
   - IFS Coatings powder requirement calculator：喷粉用量以待喷涂总表面积为输入。
   - Reliant Finishing Systems powder coating coverage：粉末成本可按零件表面积计算。
   - Birchwood Technologies black oxide 资料：黑氧化运营成本以每磅 finished work 描述。
   - Santa Clara Plating black oxide 价目表：体现黑氧化最低收费和重量/尺寸约束。
4. 最终落地时，行业默认只做 first-pass，正式规则必须优先来自供应商报价和公司历史订单。

## 14. 开发任务拆分

1. 新增 `SurfaceTreatmentPriceRule` 数据结构。
2. 新增 `SURFACE_TREATMENT_PRICING_RULES`，支持多单位。
3. 新增 `resolve_surface_treatment_rule()`。
4. 新增 `calculate_surface_treatment_quantity()`。
5. 改造表处 quantity 生成逻辑：不再固定调用 `calculate_surface_treatment_area()`。
6. 改造表处 quote item：记录 `pricing_basis` 和 basis trace。
7. 增加风险码。
8. 增加单元测试。
9. 增加 32 套样件的新旧表处差异审计脚本。
10. 灰度开关：`PRICE_SURFACE_TREATMENT_PRICING_V2=1`。

