# Support for dynamic queries

Many bespoke CLI subcommands for reporting and analytics do not scale as query needs evolve. Instead, we provide a restricted, read-only SQL interface that allows agents to construct and execute controlled queries against the receipt database without requiring a large number of specialized reporting commands. This allows the agent to propose SQL queries for advanced analytics while keeping the CLI surface area small and predictable.

The `sql` subcommand is intentionally designed as an **agent-facing interface**, not a human-oriented CLI. The interface therefore prioritizes deterministic behavior, strict validation, and machine-readable output over human convenience. 

## A subcommand for querying data

The querying interface is exposed via the `receipt-processor sql` subcommand, which supports controlled raw SQL execution.

* accepts SQL via `--query` (only); stdin is intentionally not supported to simplify validation and ensure the command always receives a single explicit statement
* read-only by default
* only allows a single statement
* only allows a single exact `SELECT` statement
* does not allow `WITH`, comments, semicolons, or leading/trailing whitespace in the query value
* rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, `PRAGMA`, or any other non-SELECT statements
* returns JSON only (as the output is intended only for agents, humans can just run the sqlite command line tool)

Example UX:

```bash
receipt-processor sql --format json --query 'select category, round(sum(line_total),2) as eur from receipt_items where tx_date between "2026-02-01" and "2026-02-29" group by category order by eur desc'
```

## Guardrails

Proposed guardrails:

* reject the query unless it is exactly equal to its original input after validation rules are applied; leading or trailing whitespace is not allowed
* reject semicolons and all SQL comments (`--`, `/* */`)
* parse and validate exactly one statement
* require that the parsed statement type is `SELECT`
* denylist/allowlist parser for SQL tokens as a second layer of validation
* `sqlite3.connect("file:...?...mode=ro", uri=True)` for readonly mode
* maximum execution time enforced via SQLite progress handler or timeout
* default row limit (e.g. `LIMIT 5000` unless user overrides)
* for large result sets, require or strongly encourage `ORDER BY` so output is deterministic

## Schema introspection commands

These commands are intentionally separate from the SQL execution interface so that agents do not need to query `sqlite_master` or other internal SQLite metadata tables directly. This improves safety, keeps the SQL surface minimal, and provides a predictable way for agents to discover schema information.

For agentic integration, agents must be able to discover table schemas including column names, columns descriptions, data types, etc.

To help the agent write SQL safely, the CLI should provide these as top-level commands:

* `receipt-processor schema`: include tables and columns
* `receipt-processor describe <table>`
* `receipt-processor sample <table> --limit 5`

That way an agent can ask questions such as “what fields are available to query for meat items?” without needing to inspect the database directly.

## Output format

JSON should be the primary supported format.

The JSON output should use a canonical structure so agents can consume it predictably. A suitable shape would be:

```json
{
  "columns": ["category", "eur"],
  "rows": [
    ["meat", 42.15],
    ["dairy", 18.90]
  ],
  "meta": {
    "row_count": 2,
    "truncated": false,
    "limit_applied": 5000,
    "execution_ms": 12
  }
}
```

The command must return raw query rows only. Mapping SQL results back into domain objects would introduce ambiguity and hidden transformations, making agent reasoning less reliable and breaking the expectation that output should match the executed query. 
