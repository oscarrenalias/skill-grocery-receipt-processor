# AGENTS.md

## Scope
- Applies to the whole repository.
- Follow instruction priority: system/developer directives first, then this file.
- Optimize for safe, deterministic receipt-processing changes with minimal regressions.
- Assume deployment target includes small-power hardware (for example Raspberry Pi-class devices).

## Repo Facts
- Python `>=3.11`, dependency/runtime management via `uv`.
- CLI entrypoint: `receipt-processor` (`receipt_processor.cli:main`).
- Core commands: `process`, `show-receipt`, `list-receipts`, `sql`, `schema`, `describe`, `sample`.
- Persistence: SQLite at `RECEIPT_DB_PATH` (default `./data/receipts.sqlite`).
- Runtime expectation: local execution with minimal footprint and no extra system services.

## Setup
- Install: `uv sync`.
- Run CLI: `uv run receipt-processor ...`.
- Run tests: `uv run pytest -q`.
- Parsing requires `OPENAI_API_KEY`; do not assume `.env` exists.

## Safety Rules
- Never run destructive git commands unless explicitly requested.
- Never revert unrelated local changes.
- Prefer minimal diffs and preserve existing short-key schema conventions (`rid`, `adj`, `warn`, etc.).
- Keep behavior backward-compatible unless the task explicitly requests a breaking change.
- Prefer solutions that reduce memory, CPU, and disk overhead.
- Avoid introducing non-essential third-party dependencies.

## CLI Contract Invariants
- `process` always outputs JSON.
- `show-receipt` and `list-receipts` support `--format text|json|markdown`.
- Error payload contract remains: `status="error"`, `err`, `msg`, optional `receipt/items/adj/warn`.
- Success payloads stay compact and short-keyed; avoid renaming fields.
- If CLI output shape/format changes, update tests in the same change.
- Keep default outputs compact to reduce I/O and token/transport cost on constrained devices.

## Parsing/Validation Invariants
- Do not double-count totals.
- Treat unit-detail rows (for example `KPL/KG ... €/unit`) as metadata, not separate purchases.
- Treat nameless promo/discount marker rows as non-item lines.
- Preserve `partial` + warnings behavior for total mismatch and parsing uncertainty.

## Model Settings Invariants
- Reasoning-family models (`o*`) must avoid unsupported sampling params.
- Non-reasoning models may use deterministic sampling (`temperature=0`, `top_p=1`) when supported.
- Any model-setting change must include/adjust tests for both code paths.

## OpenClaw Runtime Notes
- For attachments, pass a real local file path to `process --input`.
- Do not expose local filesystem paths in end-user chat responses.
- For quick persisted inspection, prefer `show-receipt --latest`.
- For analytics workflows, prefer `schema/describe/sample/sql` instead of raw DB file handling.

## Resource-Constrained Deployment Guardrails
- Treat Raspberry Pi-class hardware as baseline environment.
- Favor standard-library and already-present dependencies over adding new packages.
- Do not require external daemons/services for core features (for example Redis, queue brokers, or separate search/index services).
- Prefer synchronous/simple execution paths unless async/concurrency is clearly required and measured.
- Keep startup and steady-state memory use low; avoid large in-memory caches by default.
- Avoid heavy model/tool chains for routine tasks; use the simplest model path that meets correctness requirements.
- Keep DB access efficient with bounded result sets and indexed lookups.
- Avoid background jobs that assume always-on high-resource environments.
- If a feature adds notable compute/storage overhead, document tradeoffs and provide an opt-in flag.

## Test Checklist
- Before finalizing code changes: `uv run pytest -q`.
- If CLI rendering changes: verify/update `tests/test_cli.py`.
- If parsing/validation changes: verify/update `tests/test_pipeline.py` and `tests/test_normalization.py`.
- If model behavior changes: verify/update `tests/test_llm_agent.py`.
