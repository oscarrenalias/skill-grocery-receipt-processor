from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_EMBED_BATCH_SIZE = 64
MAX_EMBED_BATCH_SIZE = 256
DEFAULT_EMBED_MODEL = "text-embedding-3-small"


@dataclass(frozen=True)
class ItemEmbeddingInput:
    iid: int
    fi: str
    fi_raw: str
    en: str
    raw: str
    cpath: str
    store: str
    tx_date: str
    existing_payload_hash: str | None
    existing_model: str | None
    existing_dim: int | None


def ensure_vector_schema(db_path: str, dim: int) -> None:
    if dim <= 0:
        raise ValueError("embedding dimension must be positive")

    with _connect_rw(db_path) as conn:
        _load_sqlite_vec(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS item_embedding_meta (
                iid INTEGER PRIMARY KEY,
                model TEXT NOT NULL,
                dim INTEGER NOT NULL,
                payload_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS item_embedding_vec USING vec0(embedding float[{dim}])")
        conn.commit()


def index_item_embeddings(
    *,
    db_path: str,
    openai_api_key: str,
    openai_base_url: str | None,
    model: str = DEFAULT_EMBED_MODEL,
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
    rebuild: bool = False,
    limit: int | None = None,
    dim: int | None = None,
    timeout_seconds: int = 90,
) -> dict:
    if batch_size < 1 or batch_size > MAX_EMBED_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_EMBED_BATCH_SIZE}")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")

    started = datetime.now(UTC)
    with _connect_rw(db_path) as conn:
        _load_sqlite_vec(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS item_embedding_meta (
                iid INTEGER PRIMARY KEY,
                model TEXT NOT NULL,
                dim INTEGER NOT NULL,
                payload_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        if rebuild:
            conn.execute("DROP TABLE IF EXISTS item_embedding_vec")
            conn.execute("DELETE FROM item_embedding_meta")
            conn.commit()

        rows = _fetch_items_for_embedding(conn, limit=limit)
        candidates: list[tuple[ItemEmbeddingInput, str]] = []
        for row in rows:
            item = ItemEmbeddingInput(
                iid=int(row["iid"]),
                fi=str(row["fi"] or ""),
                fi_raw=str(row["fi_raw"] or ""),
                en=str(row["en"] or ""),
                raw=str(row["raw"] or ""),
                cpath=str(row["cpath"] or ""),
                store=str(row["store"] or ""),
                tx_date=str(row["tx_date"] or ""),
                existing_payload_hash=row["payload_hash"],
                existing_model=row["model"],
                existing_dim=int(row["dim"]) if row["dim"] is not None else None,
            )
            payload = build_item_embedding_payload(item)
            payload_hash = _hash_payload(payload)
            if (
                item.existing_payload_hash == payload_hash
                and item.existing_model == model
                and (dim is None or item.existing_dim == dim)
            ):
                continue
            candidates.append((item, payload))

        if not candidates:
            duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            return {
                "status": "ok",
                "indexed": 0,
                "skipped": len(rows),
                "failed": 0,
                "duration_ms": duration_ms,
                "model": model,
                "dim": dim or 0,
                "batch_size": batch_size,
            }

        indexed = 0
        failed = 0
        skipped = len(rows) - len(candidates)
        effective_dim = dim
        openai_client = _create_openai_client(
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            timeout_seconds=timeout_seconds,
        )
        sqlite_vec = _import_sqlite_vec_module()
        now = datetime.now(UTC).isoformat()

        for start_idx in range(0, len(candidates), batch_size):
            batch = candidates[start_idx : start_idx + batch_size]
            payloads = [payload for _, payload in batch]
            try:
                resp = openai_client.embeddings.create(model=model, input=payloads)
                embeddings = [item.embedding for item in resp.data]
                if not embeddings:
                    continue
                if effective_dim is None:
                    effective_dim = len(embeddings[0])
                    conn.execute(
                        f"CREATE VIRTUAL TABLE IF NOT EXISTS item_embedding_vec USING vec0(embedding float[{effective_dim}])"
                    )
                for (item, payload), embedding in zip(batch, embeddings):
                    if effective_dim is not None and len(embedding) != effective_dim:
                        failed += 1
                        continue
                    serialized = sqlite_vec.serialize_float32(embedding)
                    payload_hash = _hash_payload(payload)
                    conn.execute(
                        "INSERT OR REPLACE INTO item_embedding_vec(rowid, embedding) VALUES (?, ?)",
                        (item.iid, serialized),
                    )
                    conn.execute(
                        """
                        INSERT INTO item_embedding_meta(iid, model, dim, payload_hash, updated_at)
                        VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(iid) DO UPDATE SET
                            model=excluded.model,
                            dim=excluded.dim,
                            payload_hash=excluded.payload_hash,
                            updated_at=excluded.updated_at
                        """,
                        (item.iid, model, effective_dim or 0, payload_hash, now),
                    )
                    indexed += 1
            except Exception:
                failed += len(batch)
        conn.commit()

    duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    return {
        "status": "ok",
        "indexed": indexed,
        "skipped": skipped,
        "failed": failed,
        "duration_ms": duration_ms,
        "model": model,
        "dim": effective_dim or 0,
        "batch_size": batch_size,
    }


def build_item_embedding_payload(item: ItemEmbeddingInput) -> str:
    fi = item.fi.strip() or item.fi_raw.strip()
    return " | ".join(
        [
            f"fi:{fi}",
            f"en:{item.en.strip()}",
            f"raw:{item.raw.strip()}",
            f"cat:{item.cpath.strip()}",
            f"store:{item.store.strip()}",
            f"date:{item.tx_date.strip()}",
        ]
    )


def _fetch_items_for_embedding(conn: sqlite3.Connection, limit: int | None) -> list[sqlite3.Row]:
    sql = """
        SELECT
            i.iid,
            i.fi,
            i.fi_raw,
            i.en,
            i.raw,
            i.cpath,
            r.store,
            r.tx_date,
            m.payload_hash,
            m.model,
            m.dim
        FROM receipt_items i
        JOIN receipts r ON r.rid = i.rid
        LEFT JOIN item_embedding_meta m ON m.iid = i.iid
        ORDER BY i.iid ASC
    """
    params: tuple[object, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    return conn.execute(sql, params).fetchall()


def _connect_rw(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_payload(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    sqlite_vec = _import_sqlite_vec_module()
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def _import_sqlite_vec_module():
    try:
        import sqlite_vec  # type: ignore
    except Exception as exc:  # pragma: no cover - import environment
        raise RuntimeError("sqlite-vec is not installed. Run `uv sync` to install dependencies.") from exc
    return sqlite_vec


def _create_openai_client(*, openai_api_key: str, openai_base_url: str | None, timeout_seconds: int):
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - import environment
        raise RuntimeError("openai package is not installed. Run `uv sync` to install dependencies.") from exc
    kwargs: dict[str, object] = {"api_key": openai_api_key, "timeout": timeout_seconds}
    if openai_base_url:
        kwargs["base_url"] = openai_base_url
    return OpenAI(**kwargs)
