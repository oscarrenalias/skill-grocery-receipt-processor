# Receipt Processor

Python CLI for extracting and structuring Finnish grocery receipt PDFs using the OpenAI Agents framework.

## Requirements

- Python 3.11+
- `uv`
- `OPENAI_API_KEY` set in environment (or `.env`)

## Install

```bash
uv sync
```

## Configuration

Copy `.env.example` to `.env` and set values.

Required:

- `OPENAI_API_KEY`

Optional:

- `OPENAI_BASE_URL`
- `RECEIPT_DB_PATH`
- `RECEIPT_DEFAULT_CURRENCY`
- `RECEIPT_PARSER_MODEL`
- `RECEIPT_ENRICH_MODEL`
- `RECEIPT_TIMEOUT_SECONDS`

## CLI

```bash
receipt-processor process --input /path/to/receipt.pdf [--persist] [--debug] [--output /path/to/result.json]
receipt-processor show-receipt (--rid <receipt_id> | --latest) [--include-raw-text] [--format text|json|markdown] [--output /path/to/result.txt]
receipt-processor list-receipts [--month YYYY-MM] [--format text|json|markdown] [--output /path/to/result.txt]
receipt-processor sql --query "<select ...>" [--output /path/to/result.json]
receipt-processor schema [--output /path/to/result.json]
receipt-processor describe <table> [--output /path/to/result.json]
receipt-processor sample <table> [--limit 5] [--output /path/to/result.json]
```

Parameters:

- `process --input <path>` Process a receipt PDF.
- `process --persist` Persist to SQLite.
  - Duplicate uploads are detected automatically (by file hash and normalized extracted-text hash) and return `status="duplicate"` with the existing `rid`.
- `process --debug` Enable debug behavior.
- `show-receipt --rid <id>` Load persisted receipt by id.
- `show-receipt --latest` Load the latest persisted receipt by transaction date/time.
- `show-receipt --include-raw-text` Include stored raw receipt text.
- `show-receipt --format text|json|markdown` Render `show-receipt` as plain text (default), JSON, or Markdown-ish text for chat integrations.
- `list-receipts` List persisted receipts for the current month by default.
- `list-receipts --month YYYY-MM` List persisted receipts for a specific month.
  - Also accepts `MM/YYYY` (for example `02/2026`), but `YYYY-MM` is recommended.
- `list-receipts --format text|json|markdown` Render `list-receipts` as plain text (default), JSON, or Markdown-ish text for chat integrations.
- `sql --query "<select ...>"` Run a restricted read-only SQL query (JSON output only).
- `schema` List queryable tables and columns (JSON output only).
- `describe <table>` Describe one queryable table (JSON output only).
- `sample <table> --limit <n>` Return a small sample row set from one queryable table (JSON output only).
- `--output <path>` Also write rendered output to file.

`process` always prints structured JSON to stdout.  
`show-receipt` prints plain text by default, JSON when `--format json`, and Markdown-ish text when `--format markdown`.
`list-receipts` prints plain text by default, JSON when `--format json`, and Markdown-ish text when `--format markdown`.
`sql`, `schema`, `describe`, and `sample` always print JSON.

`show-receipt --format text` output includes:

- Human-readable receipt fields (`Receipt ID`, `Store`, `Address`, `Transaction Date`, etc.)
- A fixed-width ASCII table for line items:
  - `Item (Finnish) | Unit | Quantity | Unit Price | Line Total`
- A fixed-width ASCII table for adjustments when present
- Optional `Raw Text` section when `--include-raw-text` is provided

`show-receipt --format markdown` output includes:

- Simple Markdown-ish formatting (`*bold*`, `` `code` ``, fenced code block)
- Raw dynamic content (no Telegram-specific escaping). Downstream systems (for example OpenClaw) should handle platform-specific conversion/escaping.
- Single payload output (chunking/splitting is expected to be handled by OpenClaw)

## Compact JSON format

Top-level success keys:

- `status`, `rid`, `store`, `tx_date`, `total`, `n_items`, `n_adj`, `warn`, `dup_match` (for `status="duplicate"`)

Top-level error keys:

- `status`, `err`, `msg`, `receipt`, `items`, `adj`, `warn`

Item examples use short keys such as:

- `fi`, `en`, `qty`, `utype`, `raw_uom`, `uom`, `line_total`, `loyalty_type`, `is_weighted`

Default-valued fields are omitted to reduce payload size.

## SQL Query Guardrails

- `sql` accepts query text via `--query` only.
- Query must be a single `SELECT` statement.
- Query must not include leading/trailing whitespace, semicolons, SQL comments, or `WITH`.
- Non-read keywords are rejected (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, `PRAGMA`, etc.).
- Only domain tables are allowed: `receipts`, `receipt_items`, `receipt_adjustments`.
- Default row limit is applied when omitted (`LIMIT 5000`).

Canonical JSON output for tabular results (`sql` and `sample`):

```json
{
  "status": "ok",
  "columns": ["category", "eur"],
  "rows": [
    ["meat", 42.15],
    ["dairy", 18.9]
  ],
  "meta": {
    "row_count": 2,
    "truncated": false,
    "limit_applied": 5000,
    "execution_ms": 12
  }
}
```

## Example

```bash
uv run receipt-processor \
  process \
  --input ./samples/receipt.pdf \
  --persist \
  --debug
```
