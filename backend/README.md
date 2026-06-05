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

AI assistance is a replaceable mock service in the first phase. Set `use_ai`
to `true` in the parse request to save mock normalization and risk explanation
outputs. The mock service does not calculate prices, change price rules, or
modify process results.

Parser implementations are selected by `PRICE_PARSER_MODE`:

```text
auto  # default; try real parsers first, then fallback to mock with PARSER_FALLBACK_USED
mock  # use mock PDF/STEP parsers only
real  # use real parsers only; failures create *_PARSE_FAILED risks
```

`RealPdfParser` uses PyMuPDF for the first text-layer-only implementation. It
extracts text pages, text blocks, field evidence, field confidence, and rule
risks for drawing number, part name, material, weight, scale, treatments,
tolerances, roughness, and technical requirements. Scanned PDFs without a text
layer still fail real parsing and can fallback in `auto` mode.

`RealStepParser` is still an interface placeholder until CadQuery/pythonOCC is
added behind the same parser interface.

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
