# Backend

FastAPI + SQLite service for B1 file upload and binding.

Initial responsibilities:

- Quote task API shell.
- File upload API.
- SQLite persistence.
- Local file storage under `uploads/`.

## Database

Initialize the local SQLite database:

```bash
python -m backend.app.database
```

The development database is created at:

```text
backend/data/price_overview.sqlite3
```

Seed or repair the default development task with UTF-8 Chinese test data:

```bash
python -m backend.app.dev_seed
```

Use this instead of manually inserting Chinese text through a PowerShell
pipeline when you see `????` in `customer_name` or `part_name`.

## File Storage

Uploaded files are stored by task and file type:

```text
uploads/
  task_001/
    pdf/
      v1_file_xxx_drawing.pdf
    step/
      v1_file_xxx_model.step
    attachment/
      v1_file_xxx_note.txt
```

The original filename is kept in the database. The physical filename includes
the version and `file_id` so new versions never overwrite old files.

## Run API

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

Start the FastAPI service:

```bash
uvicorn backend.app.main:app --reload
```

Upload endpoint:

```text
GET /api/quote-tasks/{task_id}
```

Returns the task, file list, parse result, current risks, and latest quote.

Upload endpoint:

```text
POST /api/quote-tasks/{task_id}/files
```

Form fields:

- `file`
- `file_type`: `pdf`, `step`, or `attachment`
- `uploaded_by`: optional, defaults to `system`

Uploads are limited to 50 MB per file. Oversized files are rejected before a
valid `part_file` record is created.

File records keep two independent statuses:

- `status`: `uploaded`, `invalid`, or `deleted`.
- `parse_status`: `not_parsed`, `parsed`, `failed`, or `skipped`.

Mark a file invalid or logically deleted:

```text
POST /api/quote-tasks/{task_id}/files/{file_id}/invalidate
DELETE /api/quote-tasks/{task_id}/files/{file_id}
```

Invalid and deleted files remain in history, but they are not selected by the
mock parser. A successful parse marks the consumed latest PDF/STEP records as
`parsed`.

Mock parse endpoint:

```text
POST /api/quote-tasks/{task_id}/parse
```

Optional JSON body:

```json
{
  "parse_pdf": true,
  "parse_step": true,
  "use_ai": false,
  "pdf_file_id": "file_optional_pdf_id",
  "step_file_id": "file_optional_step_id"
}
```

When `pdf_file_id` or `step_file_id` is omitted, the parser uses the latest
`uploaded` file of that type. When provided, the file must belong to the task,
match the requested type, and have `status=uploaded`.

Read mock parse result:

```text
GET /api/quote-tasks/{task_id}/parse-result
```

AI assistance is a replaceable provider. Set `use_ai` to `true` in the parse
request to save normalization and risk explanation outputs. The AI service does
not calculate prices, change price rules, or modify process results.

AI assistance calls a real provider when configured. It does not generate mock
analysis unless `PRICE_AI_PROVIDER=mock` is explicitly set for development.
If the provider is unavailable, the main rules continue and an `ai-unavailable`
record is saved instead of fake analysis:

```powershell
$env:PRICE_AI_PROVIDER = "openai"  # auto, mock, or openai
$env:OPENAI_API_KEY = "..."
$env:PRICE_AI_MODEL = "gpt-5.5"
```

For local development, you can also create `backend/.env.local`:

```text
PRICE_AI_PROVIDER=openai
PRICE_AI_API_MODE=responses
PRICE_AI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=...
PRICE_AI_MODEL=gpt-5.5
```

The local file is ignored by git. Existing shell environment variables take
priority over values in `.env.local`.

For OpenAI-compatible providers such as DashScope, use Chat Completions mode:

```text
PRICE_AI_PROVIDER=openai
PRICE_AI_API_MODE=chat_completions
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=...
LLM_MODEL=qwen-plus
```

The OpenAI provider uses the Responses API by default and Chat Completions when
`PRICE_AI_API_MODE=chat_completions`. Parsing saves PDF field candidates and risk
explanations; pricing saves operation explanations. These records are returned
as `ai_outputs` from `GET /api/quote-tasks/{task_id}` and are displayed
read-only in the client.

Parser implementations are selected by `PRICE_PARSER_MODE`:

```text
auto  # default; try real parsers first. PDF may fallback to mock; STEP does not fallback to mock.
mock  # use mock PDF/STEP parsers only
real  # use real parsers only; failures create *_PARSE_FAILED risks
```

`VisionAssistedPdfParser` uses PyMuPDF for text-layer parsing first. It extracts
text pages, text blocks, field evidence, field confidence, field candidates, and
rule risks for drawing number, part name, material, weight, scale, treatments,
tolerances, roughness, and technical requirements. Low-confidence fields and
conflicting field candidates are returned for manual review instead of being
discarded.

The Tesseract/Pillow recognition path is no longer used. For scanned PDFs or
low-confidence text-layer results, the parser can render PDF pages to PNG and
send them to the configured multimodal model. It reuses the existing AI
provider configuration unless a PDF-specific override is set:

```text
PRICE_PDF_VISION_MODE=fallback  # off, fallback, low_confidence, always
PRICE_PDF_VISION_MODEL=...
PRICE_PDF_VISION_BASE_URL=...
PRICE_PDF_VISION_API_MODE=chat_completions
PRICE_PDF_VISION_API_KEY=...
PRICE_PDF_VISION_DPI=120
PRICE_PDF_VISION_MAX_PAGES=2
PRICE_PDF_VISION_TIMEOUT_SECONDS=90
```

If no PDF-specific model/key is set, the parser reuses `PRICE_AI_MODEL`,
`OPENAI_MODEL`, `LLM_MODEL`, and the existing AI API key variables. The default
`fallback` mode calls the multimodal parser only when text-layer parsing cannot
produce readable text. Set `PRICE_PDF_VISION_MODE=low_confidence` when you also
want image parsing to assist low-confidence text-layer fields. If image parsing
fails in `low_confidence` mode, the text-layer result is kept and a
`PDF_VISION_UNAVAILABLE` review risk is added. If text-layer parsing fails and
vision parsing is unavailable, `auto` mode can still fallback to the mock parser.

`RealStepParser` calls `standalone_step_parser.step_parser.parse_step_file` and
uses CadQuery/pythonOCC through that parser. Install `cadquery>=2.4` from
`backend/requirements.txt` before using real STEP parsing. Optional STEP parser
settings:

```text
PRICE_STEP_PARSER_BACKEND=auto  # auto, cadquery, pythonocc
PRICE_STEP_DENSITY=0.00000785   # optional, kg/mm3 by default
PRICE_STEP_DENSITY_UNIT=kg/mm3  # kg/mm3 or g/cm3
```

When STEP parsing fails in `auto` or `real` mode, the backend records a
`STEP_PARSE_FAILED` risk instead of generating mock geometry.

First-pass pricing endpoint:

```text
POST /api/quote-tasks/{task_id}/price
```

Optional JSON body:

```json
{
  "price_version": "a-basic-v1",
  "rounding_rule": "a_basic_rounding_ui_only"
}
```

Read pricing bundle:

```text
GET /api/quotes/{quote_id}
```

The first-pass pricing endpoint builds a contract-compatible bundle:
`process_route`, `quantity_result`, and `quote_result`. The built-in pricing
core is a bridge implementation for A/B integration and should be replaced by
A-side production rules when available.
Each call creates a new `quote_id`; manual overrides on an older quote are not
copied to the newly generated quote.

Manual override endpoint:

```text
POST /api/quotes/{quote_id}/overrides
```

JSON body:

```json
{
  "target_type": "quote_item",
  "target_id": "mock_item_process",
  "field": "amount",
  "old_value": 450,
  "new_value": 500,
  "reason": "mock adjustment reason",
  "operator_id": "user_001"
}
```

The override endpoint records the override and updates display-facing final values.
It does not overwrite `system_amount` or the system initial quote. The first
phase supports quote item amount/unit price adjustments, quantity value
adjustments, final quote adjustments, and risk confirmation records.

Confirm quote endpoint:

```text
POST /api/quotes/{quote_id}/confirm
```

JSON body:

```json
{
  "confirmed_total_amount": 1200.0,
  "confirmed_by": "user_001",
  "confirm_note": "reviewed operations and prices"
}
```

Confirmation fails when the quote is already confirmed/voided or when an
unresolved `blocking` risk exists. A successful confirmation sets the quote and
task status to `confirmed`; later overrides are rejected as read-only.

Export pricing bundle:

```text
POST /api/quotes/{quote_id}/export
GET /api/exports/{export_id}/download
```

The first-phase export is JSON. It includes `part_feature`, `process_route`,
`quantity_result`, and `quote_result` in one payload.
