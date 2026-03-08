import hashlib
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import insert

from receipt_processor.db import create_engine_and_init, receipt_items, receipts
from receipt_processor.semantic_search import semantic_search_items


def _seed_db_with_item(db_path: str) -> None:
    engine = create_engine_and_init(db_path)
    with engine.begin() as conn:
        conn.execute(
            insert(receipts),
            [
                {
                    "rid": "r1",
                    "doc_hash": hashlib.sha256(b"r1").hexdigest(),
                    "text_hash": hashlib.sha256(b"text-r1").hexdigest(),
                    "src": "seed.pdf",
                    "store": "K-Market",
                    "addr": "",
                    "tx_date": "2026-03-01",
                    "tx_time": "12:00",
                    "cur": "EUR",
                    "total": 2.9,
                    "raw_text": "raw",
                    "raw_payload": "{}",
                    "extract": "seed",
                    "status": "ok",
                    "created_at": "2026-03-07T00:00:00+00:00",
                }
            ],
        )
        conn.execute(
            insert(receipt_items),
            [
                {
                    "rid": "r1",
                    "idx": 0,
                    "raw": "Myllyn Paras makaroni",
                    "fi_raw": "Myllyn Paras makaroni",
                    "fi": "Myllyn Paras makaroni",
                    "en": "Myllyn Paras macaroni",
                    "c1": "food",
                    "c2": "dry_goods",
                    "c3": "pasta_rice_grains",
                    "cpath": "food > dry_goods > pasta_rice_grains",
                    "qty": 1.0,
                    "utype": "unit",
                    "raw_uom": "kpl",
                    "uom": "piece",
                    "uom_qty": 1.0,
                    "unit_price": 2.9,
                    "line_total": 2.9,
                    "loy_disc": 0.0,
                    "loyalty_type": "",
                    "is_weighted": False,
                    "is_return": False,
                    "conf": 0.9,
                    "notes": "",
                }
            ],
        )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE item_embedding_vec(rowid INTEGER PRIMARY KEY, embedding BLOB NOT NULL, distance REAL, k INTEGER)"
        )
        conn.execute("INSERT INTO item_embedding_vec(rowid, embedding, distance, k) VALUES (1, X'0102', 0.0, 10)")
        conn.commit()


def test_semantic_search_items_happy_path(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "receipts.sqlite")

    class _FakeCursor:
        description = [("iid",), ("distance",), ("fi",)]

        def fetchall(self):
            return [(1, 0.11, "Myllyn Paras makaroni")]

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def enable_load_extension(self, enabled: bool) -> None:
            _ = enabled

        def execute(self, sql: str, params: tuple[object, ...]):
            _ = (sql, params)
            return _FakeCursor()

    monkeypatch.setattr("receipt_processor.semantic_search._connect_ro", lambda _: _FakeConn())
    monkeypatch.setattr("receipt_processor.semantic_search._load_sqlite_vec", lambda conn: None)
    monkeypatch.setattr(
        "receipt_processor.semantic_search._import_sqlite_vec_module",
        lambda: SimpleNamespace(serialize_float32=lambda emb: b"serialized"),
    )
    monkeypatch.setattr(
        "receipt_processor.semantic_search._create_openai_client",
        lambda **kwargs: SimpleNamespace(
            embeddings=SimpleNamespace(create=lambda **_kw: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]))
        ),
    )

    out = semantic_search_items(
        db_path=db_path,
        openai_api_key="sk-test",
        openai_base_url=None,
        model="text-embedding-3-small",
        query_text="pasta like items",
        k=10,
        max_distance=None,
        timeout_seconds=90,
    )

    assert out["status"] == "ok"
    assert out["query"]["text"] == "pasta like items"
    assert "distance" in out["columns"]
    assert out["rows"] == [[1, 0.11, "Myllyn Paras makaroni"]]
    assert out["meta"]["limit_applied"] == 10


def test_semantic_search_items_rejects_empty_text(tmp_path) -> None:
    db_path = str(tmp_path / "receipts.sqlite")
    create_engine_and_init(db_path)
    with pytest.raises(ValueError, match="query text is required"):
        semantic_search_items(
            db_path=db_path,
            openai_api_key="sk-test",
            openai_base_url=None,
            model="text-embedding-3-small",
            query_text="  ",
            k=10,
            max_distance=None,
            timeout_seconds=90,
        )
