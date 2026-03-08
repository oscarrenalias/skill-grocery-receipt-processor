from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

from receipt_processor.db import receipt_adjustments, receipt_items, receipts

DEFAULT_SQL_LIMIT = 5000
DEFAULT_SAMPLE_LIMIT = 5
MAX_SAMPLE_LIMIT = 100
QUERY_TIMEOUT_MS = 3000

DOMAIN_TABLES: dict[str, Table] = {
    "receipts": receipts,
    "receipt_items": receipt_items,
    "receipt_adjustments": receipt_adjustments,
}

TABLE_DESCRIPTIONS = {
    "receipts": "Top-level receipt records and extraction status.",
    "receipt_items": "Normalized line items parsed from receipt rows.",
    "receipt_adjustments": "Discounts/adjustments applied at receipt or item level.",
}

_FORBIDDEN_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "attach",
    "detach",
    "pragma",
    "vacuum",
    "reindex",
    "create",
    "replace",
    "truncate",
)

_TABLE_REF_PATTERN = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)\b", flags=re.IGNORECASE)


def execute_readonly_sql(db_path: str, query: str, default_limit: int = DEFAULT_SQL_LIMIT) -> dict:
    validated_query = _validate_query(query)
    explicit_limit = _extract_limit(validated_query)
    limit_applied = explicit_limit if explicit_limit is not None else default_limit
    execution_query = validated_query if explicit_limit is not None else f"{validated_query} LIMIT {default_limit}"
    return _execute_sql_and_format(db_path, execution_query, limit_applied=limit_applied, truncated_on_limit=True)


def get_schema_summary(engine: Engine) -> dict:
    tables = [_build_table_description(table_name, table) for table_name, table in DOMAIN_TABLES.items()]
    return {"status": "ok", "tables": tables}


def describe_table(engine: Engine, table_name: str) -> dict:
    _ = engine  # kept for future dynamic introspection behavior
    table = _get_domain_table(table_name)
    return {"status": "ok", "table": _build_table_description(table_name, table)}


def sample_table(db_path: str, table_name: str, limit: int = DEFAULT_SAMPLE_LIMIT) -> dict:
    _get_domain_table(table_name)
    if limit < 1 or limit > MAX_SAMPLE_LIMIT:
        raise ValueError(f"sample limit must be between 1 and {MAX_SAMPLE_LIMIT}")
    query = f"SELECT * FROM {table_name} LIMIT {limit}"
    return _execute_sql_and_format(db_path, query, limit_applied=limit, truncated_on_limit=False)


def _build_table_description(table_name: str, table: Table) -> dict:
    columns = []
    for column in table.columns:
        columns.append(
            {
                "name": column.name,
                "type": str(column.type),
                "nullable": bool(column.nullable),
                "description": "",
            }
        )
    return {
        "name": table_name,
        "description": TABLE_DESCRIPTIONS.get(table_name, ""),
        "columns": columns,
    }


def _validate_query(query: str) -> str:
    if query != query.strip():
        raise ValueError("query must not contain leading or trailing whitespace")
    if ";" in query:
        raise ValueError("query must not contain semicolons")
    if "--" in query or "/*" in query or "*/" in query:
        raise ValueError("query must not contain SQL comments")
    if not query:
        raise ValueError("query is required")

    lowered = query.casefold()
    if not lowered.startswith("select "):
        raise ValueError("only SELECT statements are allowed")
    if re.search(r"\bwith\b", lowered):
        raise ValueError("WITH queries are not allowed")
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise ValueError(f"keyword not allowed in query: {keyword}")

    referenced_tables = _extract_table_references(query)
    disallowed = sorted({name for name in referenced_tables if name not in DOMAIN_TABLES})
    if disallowed:
        raise ValueError(f"query references disallowed tables: {', '.join(disallowed)}")
    return query


def _extract_table_references(query: str) -> set[str]:
    refs: set[str] = set()
    for match in _TABLE_REF_PATTERN.finditer(query):
        refs.add(match.group(1))
    return refs


def _extract_limit(query: str) -> int | None:
    match = re.search(r"\blimit\s+(\d+)\b", query, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _execute_sql_and_format(
    db_path: str,
    query: str,
    *,
    limit_applied: int,
    truncated_on_limit: bool,
) -> dict:
    path = Path(db_path).resolve()
    uri = f"file:{path}?mode=ro"
    start = time.perf_counter()
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = None
        conn.set_progress_handler(_build_progress_timeout_handler(start, QUERY_TIMEOUT_MS), 10000)
        cur = conn.execute(query)
        columns = [col[0] for col in (cur.description or [])]
        rows = [list(row) for row in cur.fetchall()]

    execution_ms = int((time.perf_counter() - start) * 1000)
    row_count = len(rows)
    truncated = bool(truncated_on_limit and row_count >= limit_applied)
    return {
        "status": "ok",
        "columns": columns,
        "rows": rows,
        "meta": {
            "row_count": row_count,
            "truncated": truncated,
            "limit_applied": limit_applied,
            "execution_ms": execution_ms,
        },
    }


def _build_progress_timeout_handler(start: float, timeout_ms: int):
    timeout_seconds = timeout_ms / 1000.0

    def _handler() -> int:
        if time.perf_counter() - start > timeout_seconds:
            return 1
        return 0

    return _handler


def _get_domain_table(table_name: str) -> Table:
    table = DOMAIN_TABLES.get(table_name)
    if table is None:
        allowed = ", ".join(sorted(DOMAIN_TABLES))
        raise ValueError(f"unknown table '{table_name}', allowed: {allowed}")
    return table
