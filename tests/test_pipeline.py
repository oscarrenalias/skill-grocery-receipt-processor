import hashlib
import sqlite3
from types import SimpleNamespace

from sqlalchemy import insert

from receipt_processor.db import (
    create_engine_and_init,
    find_duplicate_receipt,
    get_latest_receipt_dump,
    get_receipt_dump_by_id,
    list_receipt_summaries_by_month,
    receipts,
)
from receipt_processor.pipeline import compute_text_hash, process_receipt
from receipt_processor.schemas import LLMParseResult

class DummySettings:
    db_path = ":memory:"


def _minimal_parse_result() -> LLMParseResult:
    return LLMParseResult.model_validate(
        {
            "receipt": {
                "store": "K-Citymarket",
                "tx_date": "2026-03-01",
                "tx_time": "10:01",
                "cur": "EUR",
                "total": 2.9,
            },
            "items": [
                {
                    "raw": "Milk 2,90",
                    "fi_raw": "maito",
                    "fi": "maito",
                    "en": "milk",
                    "c1": "food",
                    "c2": "dairy_and_eggs",
                    "c3": "milk_and_cream",
                    "qty": 1,
                    "raw_uom": "KPL",
                    "uom_qty": 1,
                    "line_total": 2.9,
                    "conf": 0.9,
                }
            ],
        }
    )


def _mismatch_parse_result() -> LLMParseResult:
    data = _minimal_parse_result().model_dump(mode="json")
    data["receipt"]["total"] = 99.99
    return LLMParseResult.model_validate(data)


def test_process_receipt_ok_without_persist(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "receipt.pdf"
    pdf.write_bytes(b"dummy")

    monkeypatch.setattr("receipt_processor.pipeline.extract_text_from_pdf", lambda _: "K-Market\nYHTEENSA\n2,90")
    monkeypatch.setattr("receipt_processor.pipeline.parse_receipt_with_llm", lambda *args, **kwargs: _minimal_parse_result())

    payload = process_receipt(
        input_path=str(pdf),
        persist=False,
        debug=False,
        settings=DummySettings(),
    )

    assert payload["status"] in {"ok", "partial"}
    assert payload["n_items"] == 1


def test_process_receipt_total_mismatch_is_partial(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "receipt.pdf"
    pdf.write_bytes(b"dummy")

    monkeypatch.setattr("receipt_processor.pipeline.extract_text_from_pdf", lambda _: "K-Market\nYHTEENSA\n2,90")
    monkeypatch.setattr("receipt_processor.pipeline.parse_receipt_with_llm", lambda *args, **kwargs: _mismatch_parse_result())

    payload = process_receipt(
        input_path=str(pdf),
        persist=False,
        debug=False,
        settings=DummySettings(),
    )

    assert payload["status"] == "partial"
    assert any("Parsed totals differ from reported total" in warning for warning in payload["warn"])


def test_process_receipt_text_extraction_error(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "missing.pdf"

    payload = process_receipt(
        input_path=str(pdf),
        persist=False,
        debug=False,
        settings=DummySettings(),
    )

    assert payload["status"] == "error"
    assert payload["err"] == "TEXT_EXTRACTION_FAILED"


def test_persist_uses_compact_sqlite_schema(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "receipt.pdf"
    pdf.write_bytes(b"dummy")
    db_path = tmp_path / "receipts.sqlite"

    settings = SimpleNamespace(db_path=str(db_path))

    monkeypatch.setattr("receipt_processor.pipeline.extract_text_from_pdf", lambda _: "K-Market\nYHTEENSA\n2,90")
    monkeypatch.setattr("receipt_processor.pipeline.parse_receipt_with_llm", lambda *args, **kwargs: _minimal_parse_result())

    payload = process_receipt(
        input_path=str(pdf),
        persist=True,
        debug=False,
        settings=settings,
    )
    assert payload["status"] in {"ok", "partial"}

    conn = sqlite3.connect(db_path)
    try:
        receipt_cols = {row[1] for row in conn.execute("PRAGMA table_info(receipts)").fetchall()}
        assert {"rid", "doc_hash", "store", "tx_date", "total"}.issubset(receipt_cols)
        assert "receipt_id" not in receipt_cols

        item_cols = {row[1] for row in conn.execute("PRAGMA table_info(receipt_items)").fetchall()}
        assert {"rid", "idx", "raw_uom", "line_total", "is_weighted"}.issubset(item_cols)
        assert "raw_measure_unit" not in item_cols

        raw_payload = conn.execute("SELECT raw_payload FROM receipts LIMIT 1").fetchone()[0]
        assert "\"receipt\"" in raw_payload
        assert "\"store\"" in raw_payload
        assert "\"store_name\"" not in raw_payload
    finally:
        conn.close()


def test_get_receipt_dump_by_id_returns_structured_json(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "receipt.pdf"
    pdf.write_bytes(b"dummy")
    db_path = tmp_path / "receipts.sqlite"
    settings = SimpleNamespace(db_path=str(db_path))

    monkeypatch.setattr("receipt_processor.pipeline.extract_text_from_pdf", lambda _: "K-Market\nYHTEENSA\n2,90")
    monkeypatch.setattr("receipt_processor.pipeline.parse_receipt_with_llm", lambda *args, **kwargs: _minimal_parse_result())

    payload = process_receipt(
        input_path=str(pdf),
        persist=True,
        debug=False,
        settings=settings,
    )
    rid = payload["rid"]

    engine = create_engine_and_init(str(db_path))
    dumped = get_receipt_dump_by_id(engine, rid)
    assert dumped is not None
    assert dumped["status"] == "ok"
    assert dumped["rid"] == rid
    assert dumped["receipt"]["store"] == "K-Citymarket"
    assert isinstance(dumped["items"], list)
    assert isinstance(dumped["adj"], list)


def test_get_receipt_dump_by_id_not_found(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    dumped = get_receipt_dump_by_id(engine, "missing-rid")
    assert dumped is None


def test_get_latest_receipt_dump_orders_by_tx_date_and_time(monkeypatch, tmp_path) -> None:
    pdf_a = tmp_path / "receipt-a.pdf"
    pdf_b = tmp_path / "receipt-b.pdf"
    pdf_c = tmp_path / "receipt-c.pdf"
    pdf_a.write_bytes(b"dummy-a")
    pdf_b.write_bytes(b"dummy-b")
    pdf_c.write_bytes(b"dummy-c")
    db_path = tmp_path / "receipts.sqlite"
    settings = SimpleNamespace(db_path=str(db_path))

    def _parse(tx_date: str, tx_time: str) -> LLMParseResult:
        data = _minimal_parse_result().model_dump(mode="json")
        data["receipt"]["tx_date"] = tx_date
        data["receipt"]["tx_time"] = tx_time
        return LLMParseResult.model_validate(data)

    parse_results = iter(
        [
            _parse("2026-03-01", "09:00"),
            _parse("2026-03-01", "20:15"),
            _parse("2026-03-03", "08:05"),
        ]
    )
    extracted_texts = iter(
        [
            "K-Market\nYHTEENSA\n2,90\nA",
            "K-Market\nYHTEENSA\n2,90\nB",
            "K-Market\nYHTEENSA\n2,90\nC",
        ]
    )

    monkeypatch.setattr("receipt_processor.pipeline.extract_text_from_pdf", lambda _: next(extracted_texts))
    monkeypatch.setattr("receipt_processor.pipeline.parse_receipt_with_llm", lambda *args, **kwargs: next(parse_results))

    process_receipt(input_path=str(pdf_a), persist=True, debug=False, settings=settings)
    process_receipt(input_path=str(pdf_b), persist=True, debug=False, settings=settings)
    process_receipt(input_path=str(pdf_c), persist=True, debug=False, settings=settings)

    engine = create_engine_and_init(str(db_path))
    dumped = get_latest_receipt_dump(engine)
    assert dumped is not None
    assert dumped["receipt"]["tx_date"] == "2026-03-03"
    assert dumped["receipt"]["tx_time"] == "08:05"


def test_get_latest_receipt_dump_uses_rid_for_final_tie_break(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    common = {
        "doc_hash": "doc-hash",
        "src": "seed.pdf",
        "store": "K-Citymarket",
        "addr": "",
        "tx_date": "2026-03-01",
        "tx_time": "10:00",
        "cur": "EUR",
        "total": 2.9,
        "raw_text": "x",
        "raw_payload": "{}",
        "extract": "seed",
        "status": "ok",
        "created_at": "2026-03-06T12:00:00+00:00",
    }
    with engine.begin() as conn:
        conn.execute(insert(receipts), [{"rid": "a-rid", **common}, {"rid": "z-rid", **common, "doc_hash": "doc-hash-2"}])

    dumped = get_latest_receipt_dump(engine)
    assert dumped is not None
    assert dumped["rid"] == "z-rid"


def test_get_latest_receipt_dump_not_found(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    dumped = get_latest_receipt_dump(engine)
    assert dumped is None


def test_list_receipt_summaries_by_month_filters_and_orders(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    with engine.begin() as conn:
        conn.execute(
            insert(receipts),
            [
                {
                    "rid": "r-1",
                    "doc_hash": "doc-1",
                    "src": "a.pdf",
                    "store": "K-Citymarket",
                    "addr": "",
                    "tx_date": "2026-02-10",
                    "tx_time": "09:00",
                    "cur": "EUR",
                    "total": 2.0,
                    "raw_text": "x",
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": "2026-03-06T12:00:00+00:00",
                },
                {
                    "rid": "r-2",
                    "doc_hash": "doc-2",
                    "src": "b.pdf",
                    "store": "S-Market",
                    "addr": "",
                    "tx_date": "2026-02-28",
                    "tx_time": "20:15",
                    "cur": "EUR",
                    "total": 4.5,
                    "raw_text": "x",
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": "2026-03-06T12:01:00+00:00",
                },
                {
                    "rid": "r-3",
                    "doc_hash": "doc-3",
                    "src": "c.pdf",
                    "store": "Lidl",
                    "addr": "",
                    "tx_date": "2026-03-01",
                    "tx_time": "10:00",
                    "cur": "EUR",
                    "total": 1.5,
                    "raw_text": "x",
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": "2026-03-06T12:02:00+00:00",
                },
            ],
        )

    feb = list_receipt_summaries_by_month(engine, "2026-02")
    assert [row["rid"] for row in feb] == ["r-2", "r-1"]
    assert all(row["tx_date"].startswith("2026-02-") for row in feb)

    march = list_receipt_summaries_by_month(engine, "2026-03")
    assert [row["rid"] for row in march] == ["r-3"]


def test_process_receipt_persist_duplicate_by_doc_hash_short_circuits_parse(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    pdf = tmp_path / "receipt.pdf"
    pdf_bytes = b"same-pdf-content"
    pdf.write_bytes(pdf_bytes)
    raw_text = "K-Market\nYHTEENSA\n2,90"
    engine = create_engine_and_init(str(db_path))

    with engine.begin() as conn:
        conn.execute(
            insert(receipts),
            [
                {
                    "rid": "existing-rid",
                    "doc_hash": hashlib.sha256(pdf_bytes).hexdigest(),
                    "text_hash": compute_text_hash(raw_text),
                    "src": "existing.pdf",
                    "store": "K-Citymarket",
                    "addr": "",
                    "tx_date": "2026-03-01",
                    "tx_time": "10:00",
                    "cur": "EUR",
                    "total": 2.9,
                    "raw_text": raw_text,
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": "2026-03-06T12:00:00+00:00",
                }
            ],
        )

    settings = SimpleNamespace(db_path=str(db_path))
    monkeypatch.setattr("receipt_processor.pipeline.extract_text_from_pdf", lambda _: raw_text)

    def _fail_parse(*_args, **_kwargs):
        raise AssertionError("parse_receipt_with_llm should not be called for duplicate")

    monkeypatch.setattr("receipt_processor.pipeline.parse_receipt_with_llm", _fail_parse)

    payload = process_receipt(
        input_path=str(pdf),
        persist=True,
        debug=False,
        settings=settings,
    )

    assert payload["status"] == "duplicate"
    assert payload["rid"] == "existing-rid"
    assert payload["dup_match"] == "doc_hash"


def test_process_receipt_persist_duplicate_by_text_hash_short_circuits_parse(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    pdf = tmp_path / "receipt.pdf"
    pdf.write_bytes(b"different-pdf-content")
    raw_text = "K-Market\nYHTEENSA\n2,90"
    engine = create_engine_and_init(str(db_path))

    with engine.begin() as conn:
        conn.execute(
            insert(receipts),
            [
                {
                    "rid": "existing-rid-text",
                    "doc_hash": "1111111111111111111111111111111111111111111111111111111111111111",
                    "text_hash": compute_text_hash(raw_text),
                    "src": "existing.pdf",
                    "store": "K-Citymarket",
                    "addr": "",
                    "tx_date": "2026-03-01",
                    "tx_time": "10:00",
                    "cur": "EUR",
                    "total": 2.9,
                    "raw_text": raw_text,
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": "2026-03-06T12:00:00+00:00",
                }
            ],
        )

    settings = SimpleNamespace(db_path=str(db_path))
    monkeypatch.setattr("receipt_processor.pipeline.extract_text_from_pdf", lambda _: raw_text)

    def _fail_parse(*_args, **_kwargs):
        raise AssertionError("parse_receipt_with_llm should not be called for duplicate")

    monkeypatch.setattr("receipt_processor.pipeline.parse_receipt_with_llm", _fail_parse)

    payload = process_receipt(
        input_path=str(pdf),
        persist=True,
        debug=False,
        settings=settings,
    )

    assert payload["status"] == "duplicate"
    assert payload["rid"] == "existing-rid-text"
    assert payload["dup_match"] == "text_hash"


def test_create_engine_adds_text_hash_column_for_existing_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE receipts (
                rid TEXT PRIMARY KEY,
                doc_hash TEXT NOT NULL UNIQUE,
                src TEXT NOT NULL,
                store TEXT NOT NULL,
                addr TEXT NOT NULL,
                tx_date TEXT NOT NULL,
                tx_time TEXT NOT NULL,
                cur TEXT NOT NULL,
                total REAL NOT NULL,
                raw_text TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                extract TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE receipt_items (
                iid INTEGER PRIMARY KEY AUTOINCREMENT,
                rid TEXT NOT NULL,
                idx INTEGER NOT NULL,
                raw TEXT NOT NULL,
                fi_raw TEXT NOT NULL,
                fi TEXT NOT NULL,
                en TEXT NOT NULL,
                c1 TEXT NOT NULL,
                c2 TEXT NOT NULL,
                c3 TEXT NOT NULL,
                cpath TEXT NOT NULL,
                qty REAL NOT NULL,
                utype TEXT NOT NULL,
                raw_uom TEXT NOT NULL,
                uom TEXT NOT NULL,
                uom_qty REAL NOT NULL,
                unit_price REAL NOT NULL,
                line_total REAL NOT NULL,
                loy_disc REAL NOT NULL,
                loyalty_type TEXT NOT NULL,
                is_weighted BOOLEAN NOT NULL,
                is_return BOOLEAN NOT NULL,
                conf REAL NOT NULL,
                notes TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE receipt_adjustments (
                aid INTEGER PRIMARY KEY AUTOINCREMENT,
                rid TEXT NOT NULL,
                type TEXT NOT NULL,
                raw TEXT NOT NULL,
                amt REAL NOT NULL,
                item_idx INTEGER
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    create_engine_and_init(str(db_path))
    verify = sqlite3.connect(db_path)
    try:
        receipt_cols = {row[1] for row in verify.execute("PRAGMA table_info(receipts)").fetchall()}
        assert "text_hash" in receipt_cols
        indexes = [row[1] for row in verify.execute("PRAGMA index_list(receipts)").fetchall()]
        assert "idx_receipts_text_hash" in indexes
    finally:
        verify.close()


def test_find_duplicate_receipt_prefers_doc_hash(tmp_path) -> None:
    db_path = tmp_path / "receipts.sqlite"
    engine = create_engine_and_init(str(db_path))
    with engine.begin() as conn:
        conn.execute(
            insert(receipts),
            [
                {
                    "rid": "dup-rid",
                    "doc_hash": "doc-dup",
                    "text_hash": "text-dup",
                    "src": "seed.pdf",
                    "store": "K-Citymarket",
                    "addr": "",
                    "tx_date": "2026-03-01",
                    "tx_time": "10:00",
                    "cur": "EUR",
                    "total": 2.9,
                    "raw_text": "x",
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": "2026-03-06T12:00:00+00:00",
                }
            ],
        )

    found = find_duplicate_receipt(engine, document_hash="doc-dup", text_hash="text-dup")
    assert found is not None
    assert found["status"] == "duplicate"
    assert found["dup_match"] == "doc_hash"
