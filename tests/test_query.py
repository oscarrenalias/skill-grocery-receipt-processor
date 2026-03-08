import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert

from receipt_processor.db import create_engine_and_init, receipts
from receipt_processor.query import describe_table, execute_readonly_sql, get_schema_summary, sample_table


def _seed_receipt(engine, rid: str, tx_date: str = "2026-03-01") -> None:
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            insert(receipts),
            [
                {
                    "rid": rid,
                    "doc_hash": hashlib.sha256(rid.encode("utf-8")).hexdigest(),
                    "text_hash": hashlib.sha256(f"text-{rid}".encode("utf-8")).hexdigest(),
                    "src": "seed.pdf",
                    "store": "K-Citymarket",
                    "addr": "",
                    "tx_date": tx_date,
                    "tx_time": "10:00",
                    "cur": "EUR",
                    "total": 2.9,
                    "raw_text": "x",
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": now,
                }
            ],
        )


def test_execute_readonly_sql_returns_canonical_shape(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    _seed_receipt(engine, "a")

    out = execute_readonly_sql(str(db_path), "SELECT rid FROM receipts ORDER BY rid")
    assert out["status"] == "ok"
    assert out["columns"] == ["rid"]
    assert out["rows"] == [["a"]]
    assert set(out["meta"]) == {"row_count", "truncated", "limit_applied", "execution_ms"}
    assert out["meta"]["limit_applied"] == 5000


@pytest.mark.parametrize(
    "query",
    [
        " SELECT rid FROM receipts",
        "SELECT rid FROM receipts ",
        "SELECT rid FROM receipts;",
        "SELECT rid FROM receipts -- comment",
        "SELECT rid FROM receipts /* comment */",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "UPDATE receipts SET store='x'",
        "SELECT name FROM sqlite_master",
    ],
)
def test_execute_readonly_sql_rejects_invalid_queries(tmp_path, query: str) -> None:
    db_path = tmp_path / "receipts.sqlite"
    create_engine_and_init(str(db_path))
    with pytest.raises(ValueError):
        execute_readonly_sql(str(db_path), query)


def test_execute_readonly_sql_applies_default_limit(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    _seed_receipt(engine, "a")
    _seed_receipt(engine, "b")
    _seed_receipt(engine, "c")

    out = execute_readonly_sql(str(db_path), "SELECT rid FROM receipts ORDER BY rid", default_limit=2)
    assert out["rows"] == [["a"], ["b"]]
    assert out["meta"]["limit_applied"] == 2
    assert out["meta"]["truncated"] is True


def test_execute_readonly_sql_honors_explicit_limit(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    _seed_receipt(engine, "a")
    _seed_receipt(engine, "b")

    out = execute_readonly_sql(str(db_path), "SELECT rid FROM receipts ORDER BY rid LIMIT 1")
    assert out["rows"] == [["a"]]
    assert out["meta"]["limit_applied"] == 1


def test_schema_and_describe(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))

    schema = get_schema_summary(engine)
    assert schema["status"] == "ok"
    table_names = {table["name"] for table in schema["tables"]}
    assert {"receipts", "receipt_items", "receipt_adjustments"}.issubset(table_names)

    desc = describe_table(engine, "receipts")
    assert desc["status"] == "ok"
    col_names = {column["name"] for column in desc["table"]["columns"]}
    assert {"rid", "doc_hash", "text_hash"}.issubset(col_names)


def test_describe_rejects_unknown_table(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    with pytest.raises(ValueError):
        describe_table(engine, "sqlite_master")


def test_sample_table_returns_rows(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    _seed_receipt(engine, "a")
    _seed_receipt(engine, "b")

    out = sample_table(str(db_path), "receipts", limit=1)
    assert out["status"] == "ok"
    assert "rid" in out["columns"]
    assert len(out["rows"]) == 1
    assert out["meta"]["limit_applied"] == 1


def test_sample_table_rejects_invalid_limit(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    create_engine_and_init(str(db_path))
    with pytest.raises(ValueError):
        sample_table(str(db_path), "receipts", limit=0)
