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
```

Parameters:

- `process --input <path>` Process a receipt PDF.
- `process --persist` Persist to SQLite.
- `process --debug` Enable debug behavior.
- `show-receipt --rid <id>` Load persisted receipt by id.
- `show-receipt --latest` Load the latest persisted receipt by transaction date/time.
- `show-receipt --include-raw-text` Include stored raw receipt text.
- `show-receipt --format text|json|markdown` Render `show-receipt` as plain text (default), JSON, or Markdown-ish text for chat integrations.
- `list-receipts` List persisted receipts for the current month by default.
- `list-receipts --month YYYY-MM` List persisted receipts for a specific month.
  - Also accepts `MM/YYYY` (for example `02/2026`), but `YYYY-MM` is recommended.
- `list-receipts --format text|json|markdown` Render `list-receipts` as plain text (default), JSON, or Markdown-ish text for chat integrations.
- `--output <path>` Also write rendered output to file.

`process` always prints structured JSON to stdout.  
`show-receipt` prints plain text by default, JSON when `--format json`, and Markdown-ish text when `--format markdown`.
`list-receipts` prints plain text by default, JSON when `--format json`, and Markdown-ish text when `--format markdown`.

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

- `status`, `rid`, `store`, `tx_date`, `total`, `n_items`, `n_adj`, `warn`

Top-level error keys:

- `status`, `err`, `msg`, `receipt`, `items`, `adj`, `warn`

Item examples use short keys such as:

- `fi`, `en`, `qty`, `utype`, `raw_uom`, `uom`, `line_total`, `loyalty_type`, `is_weighted`

Default-valued fields are omitted to reduce payload size.

## Example

```bash
uv run receipt-processor \
  process \
  --input ./samples/receipt.pdf \
  --persist \
  --debug
```
