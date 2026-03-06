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
receipt-processor show (--rid <receipt_id> | --latest) [--include-raw-text] [--format text|json] [--output /path/to/result.txt]
```

Parameters:

- `process --input <path>` Process a receipt PDF.
- `process --persist` Persist to SQLite.
- `process --debug` Enable debug behavior.
- `show --rid <id>` Load persisted receipt by id.
- `show --latest` Load the latest persisted receipt by transaction date/time.
- `show --include-raw-text` Include stored raw receipt text.
- `show --format text|json` Render `show` results as plain text (default) or JSON.
- `--output <path>` Also write rendered output to file.

`process` always prints structured JSON to stdout.  
`show` prints plain text by default and JSON when `--format json` is set.

`show --format text` output includes:

- Human-readable receipt fields (`Receipt ID`, `Store`, `Address`, `Transaction Date`, etc.)
- A fixed-width ASCII table for line items:
  - `Item (Finnish) | Unit | Quantity | Unit Price | Line Total`
- A fixed-width ASCII table for adjustments when present
- Optional `Raw Text` section when `--include-raw-text` is provided

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
