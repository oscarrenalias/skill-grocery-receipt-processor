from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from receipt_processor.config import Settings
from receipt_processor.db import create_engine_and_init, persist_result
from receipt_processor.errors import error_payload
from receipt_processor.llm_agent import ParseError, parse_receipt_with_llm
from receipt_processor.pdf_extract import TextExtractionError, extract_text_from_pdf
from receipt_processor.schemas import LLMParseResult, ProcessSuccess, compact_dump
from receipt_processor.validate import normalize_parse_result, validate_parse_result


_TOTAL_MARKERS = ("YHTEENSA", "YHTEENSÄ")


def process_receipt(
    *,
    input_path: str,
    persist: bool,
    debug: bool,
    settings: Settings,
) -> dict:
    source = str(Path(input_path))

    try:
        content_bytes = Path(input_path).read_bytes()
    except Exception as exc:
        return error_payload("TEXT_EXTRACTION_FAILED", f"Failed to read input PDF bytes: {exc}")

    document_hash = hashlib.sha256(content_bytes).hexdigest()

    try:
        raw_text = extract_text_from_pdf(input_path)
    except TextExtractionError as exc:
        return error_payload("TEXT_EXTRACTION_FAILED", str(exc))

    extraction_warn = _check_extracted_text(raw_text)

    try:
        parse_result = parse_receipt_with_llm(raw_text, settings=settings, debug=debug)
    except ParseError as exc:
        return error_payload("PARSE_PARTIAL", str(exc), warn=extraction_warn)

    normalize_parse_result(parse_result)
    validation = validate_parse_result(parse_result)

    warn = extraction_warn + parse_result.warn + validation.warn
    is_partial = bool(parse_result.unparsed or warn)
    status = "partial" if is_partial else "ok"
    if not validation.is_total_match:
        status = "partial"

    rid = str(uuid.uuid4())
    if persist:
        try:
            engine = create_engine_and_init(settings.db_path)
            db_status = "partial" if is_partial else "ok"
            rid = persist_result(
                engine,
                document_hash=document_hash,
                source_file=source,
                raw_text=raw_text,
                extraction_method="pypdf-native-text",
                status=db_status,
                parse_result=parse_result,
            )
        except Exception as exc:
            return error_payload(
                "PERSIST_FAILED",
                f"Failed to persist parsed receipt: {exc}",
                receipt=compact_dump(parse_result.receipt),
                items=[compact_dump(i) for i in parse_result.items],
                adj=[compact_dump(a) for a in parse_result.adj],
                warn=warn,
            )

    out = ProcessSuccess(
        status=status,
        rid=rid,
        store=parse_result.receipt.store,
        tx_date=parse_result.receipt.tx_date,
        total=parse_result.receipt.total,
        n_items=len(parse_result.items),
        n_adj=len(parse_result.adj),
        warn=warn,
    )
    payload = compact_dump(out)
    if status == "partial" or debug:
        payload["receipt"] = compact_dump(parse_result.receipt)
        payload["items"] = [compact_dump(i) for i in parse_result.items]
        payload["adj"] = [compact_dump(a) for a in parse_result.adj]
    return payload


def _check_extracted_text(raw_text: str) -> list[str]:
    warn: list[str] = []
    upper = raw_text.upper()

    if "K-" not in upper and "CITYMARKET" not in upper and "SUPERMARKET" not in upper:
        warn.append("Extracted text missing expected store header pattern")
    if not any(marker in upper for marker in _TOTAL_MARKERS):
        warn.append("Extracted text missing expected total marker (YHTEENSA/YHTEENSÄ)")
    if len(raw_text.splitlines()) < 5:
        warn.append("Extracted text has too few lines for a complete receipt")
    if not any(ch.isdigit() for ch in raw_text):
        warn.append("Extracted text missing numeric content")

    return warn


def empty_parse_result() -> LLMParseResult:
    return LLMParseResult.model_validate({"receipt": {}})
