---
name: receipt-processor
description: Process Finnish grocery receipt PDFs and inspect persisted results through the local receipt-processor CLI. Use when a user wants to parse receipt files into JSON, troubleshoot extraction/parsing mismatches, validate totals, or query a stored receipt by receipt id (rid). Trigger for requests mentioning to process a receipt file, or to query the contents of the a receipt given its receipt id, or the most recent one.
---

# Receipt Processor CLI Skill

Use the existing CLI implementation exactly as shipped in this repository.

## Installation (repo-based, no ClawHub)

This skill is intended to be used directly from this git repo.

Recommended location on an OpenClaw host:

- `~/.openclaw/workspace/skills/skill-grocery-receipt-processor/`

Quick install:

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/oscarrenalias/skill-grocery-receipt-processor.git
cd skill-grocery-receipt-processor
```

### Dependency bootstrap (uv-first)

This repo uses `uv` for reproducible installs (`uv.lock`).

```bash
# from repo root
uv sync
```

If `uv` is not installed, install it first (see https://docs.astral.sh/uv/).

### Optional fallback (venv + pip)

If you don’t want to require `uv`, you can use a standard venv instead:

```bash
# from repo root
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

Then run the CLI via `receipt-processor ...` (or keep using `uv run ...`).

## Run Commands

Run from repo root:

```bash
uv run receipt-processor process --input <pdf-path> [--persist] [--debug] [--output <json-path>]
uv run receipt-processor show-receipt (--rid <receipt-id> | --latest) [--include-raw-text] [--format text|json|markdown] [--output <path>]
uv run receipt-processor list-receipts [--month YYYY-MM] [--format text|json|markdown] [--output <path>]
uv run receipt-processor sql --query "<select ...>" [--output <json-path>]
uv run receipt-processor schema [--output <json-path>]
uv run receipt-processor describe <table> [--output <json-path>]
uv run receipt-processor sample <table> [--limit 5] [--output <json-path>]
```

Use `process` to parse a receipt PDF.  
Use `show-receipt` to read one persisted receipt record (or the latest one).
Use `sql`/`schema`/`describe`/`sample` for analytics and introspection workflows.

## File Input In OpenClaw

When the user provides a receipt file (for example a Telegram attachment):

1. Ensure the attachment exists on local disk.
2. Pass its local path directly to `--input`.
3. Prefer copying the inbound file into a stable repo-relative path (for example `samples/<name>.pdf`) before running `process`.
4. If the user references a file name only, locate it first (`rg --files | rg "<name>"`) before running `process`.

Notes:

- OpenClaw typically represents inbound attachments as a local file path such as:
  - `/home/admin/.openclaw/media/inbound/<filename>.pdf`
- `--input` requires a filesystem path, not raw PDF bytes in prompt text.
- If multiple attachments are provided:
  - Prefer the first PDF.
  - If there are multiple PDFs and the user didn’t specify which, ask which one to process.

## OpenClaw Wiring

- Trigger conditions for this skill:
  - User explicitly invokes `/receipt-processor` command in Telegram or other OpenClaw interfaces.
  - User asks to process a receipt PDF, e.g., "please process this receipt" or "can you process the attached receipt file?".
  - User asks to show a stored receipt by `rid` (unlikely, since it's a technical identifier) or the latest receipt.
- Invocation style:
  - The agent should run the dedicated CLI commands (`receipt-processor process ...`, `show-receipt ...`, `list-receipts ...`, `sql ...`, `schema ...`, `describe ...`, `sample ...`), not rely on a separate tool API.
- Attachments flow (including Telegram):
  - User sends a PDF in Telegram.
  - OpenClaw downloads the attachment to a local file path.
  - The agent uses that downloaded local path as `--input <pdf-path>`.

## Output Contract

User-facing reply guidance:

- Do **not** include local filesystem paths in chat replies (they are implementation detail and confuse users).
- Instead say: "I can provide you with the full itemized receipt—just ask." and present the parsed results.

`process` always prints JSON to stdout.  
`show-receipt` prints plain text by default, JSON when `--format json`, and Markdown-ish text when `--format markdown`.
`sql`, `schema`, `describe`, and `sample` always print JSON.

`process` success shape:

- `status`: `ok`, `partial`, or `duplicate`
- `rid`
- `store`
- `tx_date`
- `total`
- `n_items`
- `n_adj`
- `warn`
- `dup_match` (`doc_hash` or `text_hash`) when `status=duplicate`

`process` detail behavior:

- Include full `receipt`, `items`, and `adj` when `status=partial` or `--debug` is enabled.
- `ok` responses are compact summary payloads unless `--debug` is set.
- Duplicate uploads with `--persist` return `status=duplicate` and the existing `rid` without re-parsing.

`show-receipt` success shape:

- Persisted receipt payload by `rid` or latest selector (receipt fields, `items`, `adj`).
- Include stored raw OCR text only when `--include-raw-text` is set.

`show-receipt` text mode behavior (`--format text`, default):

- Header fields with descriptive names (for example `Address`, `Transaction Date`).
- Fixed-width ASCII table for items:
  - `Item (Finnish) | Unit | Quantity | Unit Price | Line Total`
- Fixed-width ASCII table for adjustments when present.

`show-receipt` markdown mode behavior (`--format markdown`):

- Uses simple Markdown-ish formatting (`*bold*`, `` `code` ``, fenced code block).
- Dynamic text is not Telegram-escaped; downstream systems (for example OpenClaw) should convert/escape as needed.
- Emits one payload string; OpenClaw is responsible for chunking/splitting long messages.

`sql` behavior:

- Accepts SQL only via `--query`.
- Allows a single read-only `SELECT` statement only.
- Rejects comments, semicolons, `WITH`, and non-read SQL keywords.
- Restricts queries to domain tables (`receipts`, `receipt_items`, `receipt_adjustments`).
- Returns canonical `columns`/`rows`/`meta` JSON payload.

Error shape:

- `status: "error"`
- `err`
- `msg`
- optional `receipt`, `items`, `adj`, `warn`

Compact payload behavior:

- Default/empty fields are omitted; consumers must handle missing keys by schema defaults.

## Environment Requirements

Set environment before running:

- `OPENAI_API_KEY` (required for `process`)
- Optional: `OPENAI_BASE_URL`
- Optional DB/runtime vars: `RECEIPT_DB_PATH`, `RECEIPT_DEFAULT_CURRENCY`, `RECEIPT_PARSER_MODEL`, `RECEIPT_ENRICH_MODEL`, `RECEIPT_TIMEOUT_SECONDS`

### Required Secrets and Config

- `OPENAI_API_KEY` can be provided in either place:
  - OpenClaw gateway/service environment variables (recommended for deployed/shared execution)
  - Local repo `.env` file (recommended for local development)
- There is no separate config file for secrets in this project.
- Resolution order for runtime values is:
  - existing process environment first
  - then `.env` loaded by `python-dotenv` for missing values

Default model intent in current code:

- parser: `o3`
- enrich: `gpt-4.1`

## Operational Guidance

1. For normal parsing, run `process` without `--debug`.
2. For mismatch troubleshooting, rerun with `--debug` to return full item and adjustment arrays.
3. For durable lookup workflows, run with `--persist`, then use returned `rid` with `show-receipt`.
4. On failures, return the JSON error payload directly and preserve `warn` entries.
