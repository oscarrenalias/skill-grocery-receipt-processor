from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine

from receipt_processor.schemas import LLMParseResult, compact_dump

metadata = MetaData()

receipts = Table(
    "receipts",
    metadata,
    Column("rid", String, primary_key=True),
    Column("doc_hash", String, nullable=False, unique=True),
    Column("src", String, nullable=False),
    Column("store", String, nullable=False),
    Column("addr", String, nullable=False),
    Column("tx_date", String, nullable=False),
    Column("tx_time", String, nullable=False),
    Column("cur", String, nullable=False),
    Column("total", Float, nullable=False),
    Column("raw_text", Text, nullable=False),
    Column("raw_payload", Text, nullable=False),
    Column("extract", String, nullable=False),
    Column("status", String, nullable=False),
    Column("created_at", String, nullable=False),
)

receipt_items = Table(
    "receipt_items",
    metadata,
    Column("iid", Integer, primary_key=True, autoincrement=True),
    Column("rid", String, ForeignKey("receipts.rid"), nullable=False),
    Column("idx", Integer, nullable=False),
    Column("raw", Text, nullable=False),
    Column("fi_raw", String, nullable=False),
    Column("fi", String, nullable=False),
    Column("en", String, nullable=False),
    Column("c1", String, nullable=False),
    Column("c2", String, nullable=False),
    Column("c3", String, nullable=False),
    Column("cpath", String, nullable=False),
    Column("qty", Float, nullable=False),
    Column("utype", String, nullable=False),
    Column("raw_uom", String, nullable=False),
    Column("uom", String, nullable=False),
    Column("uom_qty", Float, nullable=False),
    Column("unit_price", Float, nullable=False),
    Column("line_total", Float, nullable=False),
    Column("loy_disc", Float, nullable=False),
    Column("loyalty_type", String, nullable=False),
    Column("is_weighted", Boolean, nullable=False),
    Column("is_return", Boolean, nullable=False),
    Column("conf", Float, nullable=False),
    Column("notes", Text, nullable=False),
)

receipt_adjustments = Table(
    "receipt_adjustments",
    metadata,
    Column("aid", Integer, primary_key=True, autoincrement=True),
    Column("rid", String, ForeignKey("receipts.rid"), nullable=False),
    Column("type", String, nullable=False),
    Column("raw", Text, nullable=False),
    Column("amt", Float, nullable=False),
    Column("item_idx", Integer, nullable=True),
)

Index("idx_receipts_date_store", receipts.c.tx_date, receipts.c.store)


class PersistenceError(RuntimeError):
    """Raised on persistence failure."""


def create_engine_and_init(db_path: str) -> Engine:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    with engine.begin() as conn:
        _migrate_legacy_schema(conn)
    metadata.create_all(engine)
    return engine


def _table_columns(conn: Connection, table_name: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).all()
    return {str(row[1]) for row in rows}


def _migrate_legacy_schema(conn: Connection) -> None:
    receipt_cols = _table_columns(conn, "receipts")
    if not receipt_cols or "receipt_id" not in receipt_cols:
        return

    conn.execute(text("PRAGMA foreign_keys=OFF"))

    conn.execute(
        text(
            """
            CREATE TABLE receipts_v2 (
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
    )
    conn.execute(
        text(
            """
            INSERT INTO receipts_v2
            (rid, doc_hash, src, store, addr, tx_date, tx_time, cur, total, raw_text, raw_payload, extract, status, created_at)
            SELECT receipt_id, document_hash, source_file, store_name, store_address, transaction_date, transaction_time,
                   currency, reported_total_eur, raw_text, raw_payload, extraction_method, status, created_at
            FROM receipts
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE receipt_items_v2 (
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
                notes TEXT NOT NULL,
                FOREIGN KEY(rid) REFERENCES receipts_v2(rid)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO receipt_items_v2
            (rid, idx, raw, fi_raw, fi, en, c1, c2, c3, cpath, qty, utype, raw_uom, uom, uom_qty, unit_price,
             line_total, loy_disc, loyalty_type, is_weighted, is_return, conf, notes)
            SELECT receipt_id, line_index, raw_line_text, raw_name_fi, normalized_name_fi, english_name,
                   category_l1, category_l2, category_l3, category_path, quantity, unit_type, raw_measure_unit,
                   measure_unit, measure_amount, unit_price_eur, line_total_eur, loyalty_discount_amount_eur,
                   loyalty_discount_type, is_weighted_item, is_return_or_refund, confidence, parser_notes
            FROM receipt_items
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE receipt_adjustments_v2 (
                aid INTEGER PRIMARY KEY AUTOINCREMENT,
                rid TEXT NOT NULL,
                type TEXT NOT NULL,
                raw TEXT NOT NULL,
                amt REAL NOT NULL,
                item_idx INTEGER,
                FOREIGN KEY(rid) REFERENCES receipts_v2(rid)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO receipt_adjustments_v2
            (rid, type, raw, amt, item_idx)
            SELECT receipt_id, type, raw_text, amount_eur, applies_to_item_id
            FROM receipt_adjustments
            """
        )
    )

    conn.execute(text("DROP TABLE receipt_adjustments"))
    conn.execute(text("DROP TABLE receipt_items"))
    conn.execute(text("DROP TABLE receipts"))
    conn.execute(text("ALTER TABLE receipts_v2 RENAME TO receipts"))
    conn.execute(text("ALTER TABLE receipt_items_v2 RENAME TO receipt_items"))
    conn.execute(text("ALTER TABLE receipt_adjustments_v2 RENAME TO receipt_adjustments"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipts_date_store ON receipts(tx_date, store)"))
    conn.execute(text("PRAGMA foreign_keys=ON"))


def get_receipt_id_by_hash(engine: Engine, document_hash: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(select(receipts.c.rid).where(receipts.c.doc_hash == document_hash)).first()
        return str(row[0]) if row else None


def persist_result(
    engine: Engine,
    *,
    document_hash: str,
    source_file: str,
    raw_text: str,
    extraction_method: str,
    status: str,
    parse_result: LLMParseResult,
) -> str:
    existing_id = get_receipt_id_by_hash(engine, document_hash)
    if existing_id:
        return existing_id

    rid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    try:
        with engine.begin() as conn:
            conn.execute(
                insert(receipts).values(
                    rid=rid,
                    doc_hash=document_hash,
                    src=source_file,
                    store=parse_result.receipt.store,
                    addr=parse_result.receipt.addr,
                    tx_date=parse_result.receipt.tx_date,
                    tx_time=parse_result.receipt.tx_time,
                    cur=parse_result.receipt.cur,
                    total=parse_result.receipt.total,
                    raw_text=raw_text,
                    raw_payload=json.dumps(compact_dump(parse_result), ensure_ascii=True),
                    extract=extraction_method,
                    status=status,
                    created_at=now,
                )
            )

            item_rows = []
            for idx, item in enumerate(parse_result.items):
                item_rows.append(
                    {
                        "rid": rid,
                        "idx": idx,
                        "raw": item.raw,
                        "fi_raw": item.fi_raw,
                        "fi": item.fi,
                        "en": item.en,
                        "c1": item.c1,
                        "c2": item.c2,
                        "c3": item.c3,
                        "cpath": item.cpath,
                        "qty": item.qty,
                        "utype": item.utype.value,
                        "raw_uom": item.raw_uom,
                        "uom": item.uom.value,
                        "uom_qty": item.uom_qty,
                        "unit_price": item.unit_price,
                        "line_total": item.line_total,
                        "loy_disc": item.loy_disc,
                        "loyalty_type": item.loyalty_type.value,
                        "is_weighted": item.is_weighted,
                        "is_return": item.is_return,
                        "conf": item.conf,
                        "notes": item.notes,
                    }
                )
            if item_rows:
                conn.execute(insert(receipt_items), item_rows)

            adj_rows = []
            for adj in parse_result.adj:
                adj_rows.append(
                    {
                        "rid": rid,
                        "type": adj.type,
                        "raw": adj.raw,
                        "amt": adj.amt,
                        "item_idx": adj.item_idx,
                    }
                )
            if adj_rows:
                conn.execute(insert(receipt_adjustments), adj_rows)
    except Exception as exc:
        raise PersistenceError(f"Failed to persist receipt: {exc}") from exc

    return rid


def get_receipt_dump_by_id(engine: Engine, rid: str, include_raw_text: bool = False) -> dict | None:
    with engine.connect() as conn:
        receipt_row = conn.execute(select(receipts).where(receipts.c.rid == rid)).first()
        if not receipt_row:
            return None

    return _build_receipt_dump(engine, receipt_row._mapping, include_raw_text=include_raw_text)


def get_latest_receipt_dump(engine: Engine, include_raw_text: bool = False) -> dict | None:
    with engine.connect() as conn:
        receipt_row = conn.execute(
            select(receipts).order_by(
                receipts.c.tx_date.desc(),
                receipts.c.tx_time.desc(),
                receipts.c.created_at.desc(),
                receipts.c.rid.desc(),
            )
        ).first()
        if not receipt_row:
            return None

    return _build_receipt_dump(engine, receipt_row._mapping, include_raw_text=include_raw_text)


def _build_receipt_dump(engine: Engine, receipt_map: dict, include_raw_text: bool) -> dict:
    rid = str(receipt_map["rid"])
    with engine.connect() as conn:
        item_rows = conn.execute(
            select(receipt_items).where(receipt_items.c.rid == rid).order_by(receipt_items.c.idx.asc())
        ).all()
        adj_rows = conn.execute(
            select(receipt_adjustments).where(receipt_adjustments.c.rid == rid).order_by(receipt_adjustments.c.aid.asc())
        ).all()

    receipt_payload = {
        "store": receipt_map["store"],
        "addr": receipt_map["addr"],
        "tx_date": receipt_map["tx_date"],
        "tx_time": receipt_map["tx_time"],
        "cur": receipt_map["cur"],
        "total": receipt_map["total"],
    }

    items_payload = []
    for row in item_rows:
        m = row._mapping
        items_payload.append(
            {
                "raw": m["raw"],
                "fi_raw": m["fi_raw"],
                "fi": m["fi"],
                "en": m["en"],
                "c1": m["c1"],
                "c2": m["c2"],
                "c3": m["c3"],
                "cpath": m["cpath"],
                "qty": m["qty"],
                "utype": m["utype"],
                "raw_uom": m["raw_uom"],
                "uom": m["uom"],
                "uom_qty": m["uom_qty"],
                "unit_price": m["unit_price"],
                "line_total": m["line_total"],
                "loy_disc": m["loy_disc"],
                "loyalty_type": m["loyalty_type"],
                "is_weighted": bool(m["is_weighted"]),
                "is_return": bool(m["is_return"]),
                "conf": m["conf"],
                "notes": m["notes"],
            }
        )

    adj_payload = []
    for row in adj_rows:
        m = row._mapping
        adj_payload.append(
            {
                "type": m["type"],
                "raw": m["raw"],
                "amt": m["amt"],
                "item_idx": m["item_idx"],
            }
        )

    payload = {
        "status": "ok",
        "rid": rid,
        "receipt": receipt_payload,
        "items": items_payload,
        "adj": adj_payload,
    }
    if include_raw_text:
        payload["raw_text"] = receipt_map["raw_text"]
    return payload
