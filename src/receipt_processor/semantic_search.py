from __future__ import annotations

import sqlite3
import time
from pathlib import Path

MAX_K = 200


def semantic_search_items(
    *,
    db_path: str,
    openai_api_key: str,
    openai_base_url: str | None,
    model: str,
    query_text: str,
    k: int,
    max_distance: float | None,
    timeout_seconds: int,
) -> dict:
    text = query_text.strip()
    if not text:
        raise ValueError("query text is required")
    if k < 1 or k > MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    if max_distance is not None and max_distance < 0:
        raise ValueError("max_distance must be >= 0")

    start = time.perf_counter()
    client = _create_openai_client(
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
        timeout_seconds=timeout_seconds,
    )
    embedding_resp = client.embeddings.create(model=model, input=text)
    if not embedding_resp.data:
        raise RuntimeError("embedding response had no vectors")
    query_embedding = embedding_resp.data[0].embedding
    sqlite_vec = _import_sqlite_vec_module()
    serialized = sqlite_vec.serialize_float32(query_embedding)

    columns: list[str]
    rows: list[list[object]]
    with _connect_ro(db_path) as conn:
        _load_sqlite_vec(conn)
        sql = """
            SELECT
                v.rowid AS iid,
                v.distance,
                i.rid,
                i.idx,
                i.fi,
                i.en,
                i.c1,
                i.c2,
                i.c3,
                i.cpath,
                i.qty,
                i.uom,
                i.unit_price,
                i.line_total,
                r.store,
                r.tx_date,
                r.tx_time
            FROM item_embedding_vec AS v
            JOIN receipt_items AS i ON i.iid = v.rowid
            JOIN receipts AS r ON r.rid = i.rid
            WHERE v.embedding MATCH ? AND k = ?
        """
        params: list[object] = [serialized, k]
        if max_distance is not None:
            sql += " AND v.distance <= ?"
            params.append(max_distance)
        sql += " ORDER BY v.distance ASC"

        cur = conn.execute(sql, tuple(params))
        columns = [col[0] for col in (cur.description or [])]
        rows = [list(row) for row in cur.fetchall()]

    execution_ms = int((time.perf_counter() - start) * 1000)
    return {
        "status": "ok",
        "query": {
            "text": text,
            "model": model,
            "k": k,
            "max_distance": max_distance,
        },
        "columns": columns,
        "rows": rows,
        "meta": {
            "row_count": len(rows),
            "truncated": False,
            "limit_applied": k,
            "execution_ms": execution_ms,
        },
    }


def _connect_ro(db_path: str) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = None
    return conn


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
