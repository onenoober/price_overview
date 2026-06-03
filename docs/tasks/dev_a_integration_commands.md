# Dev A 联调命令

以下命令均在仓库根目录执行。

## 1. A 侧自测

```bash
python -m unittest discover -s tests -v
```

## 2. 跑 A 侧联调样本回归

```bash
python scripts/run_pricing_regression.py --manifest fixtures/integration/dev_a_samples.json --output tmp/dev_a_regression_report.json
```

输出：

```text
tmp/dev_a_regression_report.json
```

通过标准：

```text
success = true
failed = 0
```

## 3. 生成单个样本核价结果

```bash
python scripts/pricing_core_cli.py price --input fixtures/integration/part_feature_block_s45c_clean.json --output tmp/block_s45c_pricing_result.json --db tmp/dev_a_integration.sqlite
```

输出：

```text
tmp/block_s45c_pricing_result.json
tmp/dev_a_integration.sqlite
```

## 4. 查询基础字典

```bash
python scripts/pricing_core_cli.py dictionary --kind materials --output tmp/materials.json
python scripts/pricing_core_cli.py dictionary --kind operations --output tmp/operations.json
python scripts/pricing_core_cli.py dictionary --kind risk_tags --output tmp/risk_tags.json
python scripts/pricing_core_cli.py dictionary --kind units --output tmp/units.json
```

## 5. 查询当前生效价格规则

```bash
python scripts/pricing_core_cli.py price-rules --active-only --output tmp/active_price_rules.json
```

只看材料价：

```bash
python scripts/pricing_core_cli.py price-rules --active-only --price-type material --output tmp/active_material_price_rules.json
```

## 6. 生成历史样本

```bash
python scripts/pricing_core_cli.py history-sample --pricing-result tmp/block_s45c_pricing_result.json --sample-id sample_block_s45c_integration --include-summary --db tmp/dev_a_integration.sqlite --output tmp/block_s45c_history_sample.json
```

## 7. 使用 B 侧生成的 part_feature 联调

B 侧将生成的 `part_feature` 保存为：

```text
tmp/from_dev_b_part_feature.json
```

A 侧执行：

```bash
python scripts/pricing_core_cli.py price --input tmp/from_dev_b_part_feature.json --output tmp/from_dev_b_pricing_result.json --db tmp/dev_a_integration.sqlite
```

检查输出必须包含：

```text
part_feature
process_route
quantity_result
quote_result
```

## 8. 风险确认

输入可以是完整核价结果，也可以是裸 `quote_result`。

```bash
python scripts/pricing_core_cli.py confirm-risk --quote tmp/from_dev_b_pricing_result.json --risk-code HIGH_RISK_GEOMETRY --reason reviewed_by_process_engineer --operator-id user_a --output tmp/from_dev_b_risk_confirmed.json
```

## 9. 报价确认

只对无待确认风险、无待确认报价项的结果执行。

```bash
python scripts/pricing_core_cli.py confirm-quote --quote tmp/block_s45c_pricing_result.json --confirmed-by user_a --confirm-note integration_confirmed --output tmp/block_s45c_confirmed_quote.json
```
