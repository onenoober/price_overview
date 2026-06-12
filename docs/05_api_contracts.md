# API 契约

## API 原则

接口必须围绕任务、文件、解析、核价、核对、导出组织。

约束：

| 约束 | 要求 |
|---|---|
| 统一返回结构 | 所有接口必须返回 `success`、`data`、`error`。 |
| 错误结构化 | 错误必须包含 `code`、`message`、`details`。 |
| 状态可追踪 | 异步任务必须可查询状态。 |
| 契约稳定 | 修改入参出参前必须更新本文档。 |
| 不返回临时字段 | 前端不得依赖未写入文档的字段。 |

## 通用响应

成功：

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

失败：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数不合法",
    "details": []
  }
}
```

## 任务 API

### 创建报价任务

`POST /api/quote-tasks`

请求：

```json
{
  "customer_name": "客户名称",
  "part_name": "零件名称",
  "part_no": "图号",
  "quantity": 1,
  "remark": ""
}
```

响应：

```json
{
  "task_id": "task_001",
  "status": "draft",
  "created_at": "2026-06-01T10:00:00+08:00"
}
```

### 查询报价任务

`GET /api/quote-tasks/{task_id}`

响应必须包含：

| 字段 | 说明 |
|---|---|
| `task_id` | 任务 ID。 |
| `status` | 当前状态。 |
| `files` | 已上传文件。 |
| `latest_quote_id` | 最新报价 ID，可为空。 |
| `risks` | 当前风险摘要。 |

## 文件 API

### 上传文件

`POST /api/quote-tasks/{task_id}/files`

表单字段：

| 字段 | 说明 |
|---|---|
| `file` | 文件。 |
| `file_type` | `pdf`、`step`、`attachment`。 |

响应：

```json
{
  "file_id": "file_001",
  "task_id": "task_001",
  "file_type": "pdf",
  "filename": "drawing.pdf",
  "version": 1,
  "status": "uploaded"
}
```

约束：

- 同一任务允许多个版本文件。
- 文件校验失败必须返回结构化错误。
- 缺 PDF 或缺 STEP 不阻塞初始报价，但必须生成风险。

## 解析 API

### 启动解析

`POST /api/quote-tasks/{task_id}/parse`

请求：

```json
{
  "parse_pdf": true,
  "parse_step": true,
  "use_ai": true
}
```

响应：

```json
{
  "parse_job_id": "parse_job_001",
  "status": "queued"
}
```

### 查询解析结果

`GET /api/quote-tasks/{task_id}/parse-result`

响应：

```json
{
  "pdf_extract_result": {},
  "step_feature_result": {},
  "part_feature": {},
  "risks": []
}
```

约束：

- `part_feature` 必须符合 `docs/contracts/part_feature.schema.json`。
- 解析失败时必须返回可展示错误和可继续处理状态。

## 核价 API

### 生成初始报价

`POST /api/quote-tasks/{task_id}/price`

请求：

```json
{
  "price_version": "active",
  "rounding_rule": "nearest_1",
  "use_market_price_search": true,
  "material_region": "south_china"
}
```

响应：

```json
{
  "quote_id": "quote_001",
  "status": "priced",
  "quote_result": {}
}
```

约束：

- 响应中的 `quote_result` 必须符合 `docs/contracts/quote_result.schema.json`。
- 有必确认风险时状态必须为 `pending_review`。
- 不得因为价格缺失而静默填 0，必须生成 `MISSING_PRICE` 风险。
- `use_market_price_search=true` 时，材料单价可通过 SearXNG 实时搜索候选价；搜索价必须标记为待复核，不得绕过人工确认。

### 查询报价结果

`GET /api/quotes/{quote_id}`

响应：

```json
{
  "quote_result": {}
}
```

## 核对 API

### 保存人工修改

`POST /api/quotes/{quote_id}/overrides`

请求：

```json
{
  "target_type": "quote_item",
  "target_id": "item_001",
  "field": "amount",
  "old_value": 120.0,
  "new_value": 150.0,
  "reason": "高精度孔加工难度较高",
  "operator_id": "user_001"
}
```

响应：

```json
{
  "override_id": "override_001",
  "quote_id": "quote_001",
  "saved": true
}
```

约束：

- `reason` 必填。
- 不得覆盖系统初始值。
- 修改必须进入 `manual_overrides`。

### 确认报价

`POST /api/quotes/{quote_id}/confirm`

请求：

```json
{
  "confirmed_total_amount": 1200.0,
  "confirmed_by": "user_001",
  "confirm_note": "已核对工序和价格"
}
```

响应：

```json
{
  "quote_id": "quote_001",
  "status": "confirmed",
  "confirmed_at": "2026-06-01T10:30:00+08:00"
}
```

约束：

- 存在未确认的 `blocking` 风险时不得确认。
- 确认后报价结果只读，后续修改必须生成新版本或撤销确认。

## 导出 API

### 导出报价明细

`POST /api/quotes/{quote_id}/export`

请求：

```json
{
  "format": "xlsx",
  "include_initial_quote": true,
  "include_manual_overrides": true,
  "include_risks": true
}
```

响应：

```json
{
  "export_id": "export_001",
  "download_url": "/api/exports/export_001/download"
}
```

约束：

- 导出内容必须包含初始报价和最终确认价。
- 导出必须包含修改记录。

## 字典与规则 API

### 查询材料字典

`GET /api/dictionaries/materials`

### 查询工序字典

`GET /api/dictionaries/operations`

### 查询价格规则

`GET /api/price-rules?status=active`

### 导入价格规则

`POST /api/price-rules/import`

约束：

- 导入价格不得直接生效，除非明确传入审核通过状态。
- 价格规则必须有生效日期和来源。

