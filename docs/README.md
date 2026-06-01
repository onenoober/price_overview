# 开发文档入口

## 文档使用原则

开发时只读与当前任务相关的文档，不需要每次读完全部文档。

共同必读：

1. [00_project_overview.md](00_project_overview.md)
2. [01_architecture.md](01_architecture.md)
3. [03_ai_coding_rules.md](03_ai_coding_rules.md)
4. [04_data_contracts.md](04_data_contracts.md)
5. [05_api_contracts.md](05_api_contracts.md)

## 两个开发者分配

| 开发者 | 主责 | 任务文档 |
|---|---|---|
| A | 核价核心、规则、计算、价格、后端数据闭环。 | [tasks/developer_a_pricing_core.md](tasks/developer_a_pricing_core.md) |
| B | 文件、解析、AI 辅助、核对页面、导出。 | [tasks/developer_b_parser_ui.md](tasks/developer_b_parser_ui.md) |
| A/B 共同 | 数据契约、接口契约、联调、验收。 | [tasks/integration_checklist.md](tasks/integration_checklist.md) |

更详细的阅读分配见：

- [tasks/developer_document_map.md](tasks/developer_document_map.md)
- [tasks/preparation_checklist.md](tasks/preparation_checklist.md)

## 开发前最小阅读

A 开发前最少阅读：

1. [00_project_overview.md](00_project_overview.md)
2. [03_ai_coding_rules.md](03_ai_coding_rules.md)
3. [04_data_contracts.md](04_data_contracts.md)
4. [tasks/developer_a_pricing_core.md](tasks/developer_a_pricing_core.md)

B 开发前最少阅读：

1. [00_project_overview.md](00_project_overview.md)
2. [03_ai_coding_rules.md](03_ai_coding_rules.md)
3. [04_data_contracts.md](04_data_contracts.md)
4. [tasks/developer_b_parser_ui.md](tasks/developer_b_parser_ui.md)

联调前共同阅读：

1. [05_api_contracts.md](05_api_contracts.md)
2. [tasks/integration_checklist.md](tasks/integration_checklist.md)
3. [06_testing_and_acceptance.md](06_testing_and_acceptance.md)

