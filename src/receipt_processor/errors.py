from __future__ import annotations

from receipt_processor.schemas import ProcessError, compact_dump


def error_payload(
    err: str,
    msg: str,
    *,
    receipt: dict | None = None,
    items: list[dict] | None = None,
    adj: list[dict] | None = None,
    warn: list[str] | None = None,
) -> dict:
    payload = ProcessError(
        status="error",
        err=err,
        msg=msg,
        receipt=receipt,
        items=items or [],
        adj=adj or [],
        warn=warn or [],
    )
    return compact_dump(payload)
