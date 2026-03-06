from receipt_processor.schemas import LLMParseResult
from receipt_processor.taxonomy import ALLOWED_C3, normalize_category
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


def test_normalize_category_from_c3_mapping() -> None:
    l1, l2, l3, path = normalize_category("misc", "x", "milk_and_cream")
    assert (l1, l2, l3) == ("food", "dairy_and_eggs", "milk_and_cream")
    assert path == "food > dairy_and_eggs > milk_and_cream"


def test_normalize_category_unknown_c3_falls_back() -> None:
    l1, l2, l3, path = normalize_category("food", "meat_and_seafood", "beef")
    assert (l1, l2, l3) == ("other", "unknown", "uncategorized")
    assert path == "other > unknown > uncategorized"


def test_allowed_c3_unique_values() -> None:
    assert len(ALLOWED_C3) == len(set(ALLOWED_C3))


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
    assert result.items[0].c3 == "uncategorized"
    assert result.items[0].c2 == "unknown"
    assert len(result.adj) == 1
    assert validation.is_total_match is True


def test_normalize_parse_result_derives_c1_c2_from_c3() -> None:
    result = LLMParseResult.model_validate(
        {
            "receipt": {"total": 1.0},
            "items": [
                {
                    "raw": "Kanafilee 1,00",
                    "fi_raw": "Kanafilee",
                    "line_total": 1.0,
                    "c1": "other",
                    "c2": "unknown",
                    "c3": "poultry",
                }
            ],
        }
    )

    normalize_parse_result(result)
    item = result.items[0]
    assert item.c1 == "food"
    assert item.c2 == "meat_and_seafood"
    assert item.c3 == "poultry"
    assert item.cpath == "food > meat_and_seafood > poultry"
