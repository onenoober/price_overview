# Client

PyQt client for the C/S workflow.

Initial responsibilities:

- Select PDF, STEP/STP, and attachment files.
- Upload files to the FastAPI backend.
- Display uploaded file records and file-related risks.

The `Files` tab provides:

- File type selection: `pdf`, `step`, `attachment`.
- Local file selection.
- Upload operator input.
- Upload, refresh, mark invalid, and logical delete actions.
- File table columns for file ID, filename, file type, version, file status,
  parse status, whether it is referenced by the current parse result, upload
  time, uploader, and storage path.

The `Part Feature` and `Risks` tabs provide:

- PDF and STEP selection controls for parsing a specific uploaded version, with
  automatic latest-file selection as the default. PDF and STEP can be enabled
  independently, so a task can parse only PDF, only STEP, or both. Selecting an
  uploaded PDF or STEP row in the file table also switches the corresponding
  parse selector.
- Structured material, dimension, volume, area, weight, treatment, and part type
  display.
- Hole and precision requirement tables.
- Risk table with risk code, level, review flag, message, and evidence source.
- Refresh action backed by `GET /api/quote-tasks/{task_id}/parse-result`.

The `Quote` tab provides:

- First-pass pricing bundle generation through `POST /api/quote-tasks/{task_id}/price`.
- Confirmation before generating a new quote when the current task already
  has a `latest_quote_id`.
- Quote refresh through `GET /api/quotes/{quote_id}`.
- Process route and quantity result tables for the A/B integration bundle.
- Quote summary fields for material, process, surface treatment, management,
  tax, risk surcharge, system calculated amount, initial quote, manual
  adjustment, and final confirmed quote.
- Quote item and quote risk review tables.
- Manual override dialog backed by `POST /api/quotes/{quote_id}/overrides`.
- Manual override records with target, field, old value, new value, reason,
  operator, and time.
- Quantity value adjustments and risk confirmations from the quote review page.
- Quote confirmation dialog backed by `POST /api/quotes/{quote_id}/confirm`.
  Quotes with unresolved `blocking` risks cannot be confirmed, and confirmed or
  voided quotes are shown as read-only for further edits.

Interaction feedback:

- Upload actions switch to the `Files` tab after success.
- Parse switches to the `Part Feature` tab after success.
- Pricing and manual overrides switch to the `Quote` tab after success.
- Export shows the saved JSON path after success.
- Table cells show full text in tooltips when long values are truncated.

## Run

Install client dependencies:

```powershell
pip install -r client/requirements.txt
```

Start the backend in one terminal:

```powershell
uvicorn backend.app.main:app --reload
```

Start the PyQt client in another terminal:

```powershell
python -m client.main
```

The default backend URL is `http://127.0.0.1:8000`. Use `刷新任务` to load
existing tasks, or `新建任务` to create a task before uploading real PDF/STEP
files. `task_001` is only a seeded demo task.
