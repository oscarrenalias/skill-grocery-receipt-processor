from receipt_processor.schemas import LLMParseResult
from receipt_processor.taxonomy import normalize_category
from receipt_processor.units import canonicalize_unit
from receipt_processor.validate import normalize_number, normalize_parse_result, validate_parse_result


def test_normalize_number_comma_decimal() -> None:
    assert normalize_number("7,26") == 7.26


def test_normalize_number_trailing_minus() -> None:
    assert normalize_number("0,52-") == -0.52


def test_canonicalize_unit_supported() -> None:
    measure, unit_type = canonicalize_unit("KPL")
    assert measure.value == "piece"
    assert unit_type.value == "piece"


def test_canonicalize_unit_unknown() -> None:
    measure, unit_type = canonicalize_unit("XYZ")
    assert measure.value == "unknown"
    assert unit_type.value == "unknown"


def test_normalize_category_outside_allowed_l1() -> None:
    l1, l2, l3, path = normalize_category("misc", "x", "y")
    assert (l1, l2, l3) == ("other", "unknown", "uncategorized")
    assert path == "other > unknown > uncategorized"


def test_normalize_parse_result_drops_non_item_lines_and_fixes_total() -> None:
    result = LLMParseResult.model_validate(
        {
            "receipt": {"total": 33.65},
            "items": [
                {"raw": "Valio Keittion rahka 200g 5,94", "fi_raw": "Valio Keittion rahka", "line_total": 5.94},
                {"raw": "3 KPL 1,98 EUR/KPL", "line_total": 5.94, "qty": 3, "raw_uom": "KPL"},
                {"raw": "Ehrmann maitorahka 250g 0% 5,94", "fi_raw": "Ehrmann maitorahka", "line_total": 5.94},
                {"raw": "6 KPL 0,99 EUR/KPL", "line_total": 5.94, "qty": 6, "raw_uom": "KPL"},
                {"raw": "Muu tuote 21,77", "fi_raw": "Muu tuote", "line_total": 21.77},
                {"raw": "2*PLUSSA-TASAERA 3 KPL/2,50 EUR", "line_total": 2.5, "loyalty_type": "TASAERA"},
                {"raw": "PLUSSA-ETU 0,94-", "line_total": -0.94, "loyalty_type": "PLUSSA"},
            ],
            "adj": [{"type": "LOYALTY_DISCOUNT", "raw": "PLUSSA-ETU 0,94-", "amt": -0.94}],
        }
    )

    normalize_parse_result(result)
    validation = validate_parse_result(result)

    assert [item.raw for item in result.items] == [
        "Valio Keittion rahka 200g 5,94",
        "Ehrmann maitorahka 250g 0% 5,94",
        "Muu tuote 21,77",
    ]
    assert len(result.adj) == 1
    assert validation.is_total_match is True
