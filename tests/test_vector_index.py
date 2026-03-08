import hashlib
import sqlite3
from types import SimpleNamespace

from sqlalchemy import insert

from receipt_processor.db import create_engine_and_init, receipt_items, receipts
from receipt_processor.vector_index import ItemEmbeddingInput, build_item_embedding_payload, index_item_embeddings


def _seed_receipt_item(db_path: str) -> None:
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
                    "raw": "kanafilee",
                    "fi_raw": "kanafilee",
                    "fi": "kanafilee",
                    "en": "chicken fillet",
                    "c1": "food",
                    "c2": "meat_and_fish",
                    "c3": "poultry",
                    "cpath": "food > meat_and_fish > poultry",
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


def test_build_item_embedding_payload_prefers_fi_over_fi_raw() -> None:
    payload = build_item_embedding_payload(
        ItemEmbeddingInput(
            iid=1,
            fi="kanafilee",
            fi_raw="kana",
            en="chicken",
            raw="kanafilee",
            cpath="food > meat_and_fish > poultry",
            store="K-Market",
            tx_date="2026-03-01",
            existing_payload_hash=None,
            existing_model=None,
            existing_dim=None,
        )
    )
    assert payload.startswith("fi:kanafilee")
    assert "en:chicken" in payload


def test_index_item_embeddings_indexes_and_then_skips(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "receipts.sqlite")
    _seed_receipt_item(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE item_embedding_vec(rowid INTEGER PRIMARY KEY, embedding BLOB NOT NULL)")
        conn.commit()

    monkeypatch.setattr("receipt_processor.vector_index._load_sqlite_vec", lambda conn: None)
    monkeypatch.setattr(
        "receipt_processor.vector_index._import_sqlite_vec_module",
        lambda: SimpleNamespace(serialize_float32=lambda emb: b"|".join(str(v).encode("utf-8") for v in emb)),
    )
    monkeypatch.setattr(
        "receipt_processor.vector_index._create_openai_client",
        lambda **kwargs: SimpleNamespace(
            embeddings=SimpleNamespace(create=lambda **_kw: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]))
        ),
    )

    first = index_item_embeddings(
        db_path=db_path,
        openai_api_key="sk-test",
        openai_base_url=None,
        model="text-embedding-3-small",
        batch_size=16,
        dim=3,
    )
    assert first["indexed"] == 1
    assert first["skipped"] == 0
    assert first["failed"] == 0

    second = index_item_embeddings(
        db_path=db_path,
        openai_api_key="sk-test",
        openai_base_url=None,
        model="text-embedding-3-small",
        batch_size=16,
        dim=3,
    )
    assert second["indexed"] == 0
    assert second["skipped"] == 1
    assert second["failed"] == 0
