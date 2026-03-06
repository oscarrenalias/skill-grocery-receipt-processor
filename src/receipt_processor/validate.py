from __future__ import annotations

import re

from receipt_processor.schemas import LLMParseResult, ReceiptAdjustment, ReceiptItem
from receipt_processor.taxonomy import normalize_category
from receipt_processor.units import canonicalize_unit

_COMMA_DECIMAL = re.compile(r"(-?\d+),(\d+)")
_TRAILING_MINUS = re.compile(r"^(\d+(?:\.\d+)?)-$")
_UNIT_DETAIL_LINE = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*(KPL|KG|G|L|ML)\b.*(?:EUR|€)\s*/\s*(KPL|KG|G|L|ML)\b",
    re.IGNORECASE,
)
_PROMO_MARKER = re.compile(r"(PLUSSA|ETU|TASAER|KAMPANJA|ALE)", re.IGNORECASE)


class ValidationResult:
    def __init__(
        self,
        warn: list[str],
        is_total_match: bool,
        total_candidates: dict[str, float],
    ):
        self.warn = warn
        self.is_total_match = is_total_match
        self.total_candidates = total_candidates


def normalize_number(raw: str) -> float | None:
    if not raw:
        return None
    s = raw.strip().replace(" ", "")
    s = _COMMA_DECIMAL.sub(r"\1.\2", s)
    m = _TRAILING_MINUS.match(s)
    if m:
        s = f"-{m.group(1)}"
    try:
        return float(s)
    except ValueError:
        return None


def normalize_parse_result(result: LLMParseResult) -> None:
    for item in result.items:
        uom, utype = canonicalize_unit(item.raw_uom)
        if item.uom.value == "unknown":
            item.uom = uom
        if item.utype.value == "unknown":
            item.utype = utype

        c1, c2, c3, cpath = normalize_category(item.c1, item.c2, item.c3)
        item.c1 = c1
        item.c2 = c2
        item.c3 = c3
        item.cpath = cpath

    _deduplicate_non_item_lines(result)


def _has_name(item: ReceiptItem) -> bool:
    return bool(item.fi_raw.strip() or item.fi.strip())


def _is_unit_detail_line(item: ReceiptItem) -> bool:
    if _has_name(item):
        return False
    return bool(_UNIT_DETAIL_LINE.search(item.raw))


def _is_promo_or_discount_line(item: ReceiptItem) -> bool:
    if _has_name(item):
        return False
    return bool(_PROMO_MARKER.search(item.raw) or item.loyalty_type.value != "NONE")


def _deduplicate_non_item_lines(result: LLMParseResult) -> None:
    kept_items: list[ReceiptItem] = []
    dropped_count = 0

    for item in result.items:
        if _is_unit_detail_line(item):
            dropped_count += 1
            continue

        if _is_promo_or_discount_line(item):
            if item.line_total < 0:
                has_matching_adjustment = any(
                    abs(adj.amt - item.line_total) <= 0.01 and adj.raw.strip() == item.raw.strip()
                    for adj in result.adj
                )
                if not has_matching_adjustment:
                    result.adj.append(
                        ReceiptAdjustment(
                            type="LOYALTY_DISCOUNT",
                            raw=item.raw,
                            amt=item.line_total,
                            item_idx=None,
                        )
                    )
            dropped_count += 1
            continue

        kept_items.append(item)

    if dropped_count:
        result.warn.append(f"Dropped {dropped_count} non-item lines (unit-detail/promo) from item totals")
    result.items = kept_items


def validate_parse_result(result: LLMParseResult, total_tolerance: float = 0.02) -> ValidationResult:
    warn: list[str] = []

    if not result.receipt.tx_date:
        warn.append("Missing transaction date")

    if not result.items:
        warn.append("No line items extracted")

    for idx, item in enumerate(result.items):
        if not item.is_return and item.line_total < 0:
            warn.append(f"Item {idx} has negative line_total without return flag")
        if item.qty <= 0 and not item.is_return:
            warn.append(f"Item {idx} has non-positive qty")
        if item.uom.value == "unknown" and item.raw_uom:
            warn.append(f"Item {idx} has unsupported raw_uom: {item.raw_uom}")

    item_total = sum(i.line_total for i in result.items)
    adj_total = sum(a.amt for a in result.adj)
    adj_total_abs = sum(abs(a.amt) for a in result.adj)
    total_candidates = {
        "items_plus_adj": round(item_total + adj_total, 2),
        "items_only": round(item_total, 2),
        "items_plus_abs_adj": round(item_total + adj_total_abs, 2),
    }
    reported_total = round(result.receipt.total, 2)

    is_total_match = True
    if reported_total and not any(
        abs(candidate_total - reported_total) <= total_tolerance
        for candidate_total in total_candidates.values()
    ):
        warn.append(
            "Parsed totals differ from reported total "
            f"(candidates={total_candidates}, reported={reported_total})"
        )
        is_total_match = False

    return ValidationResult(
        warn=warn,
        is_total_match=is_total_match,
        total_candidates=total_candidates,
    )
