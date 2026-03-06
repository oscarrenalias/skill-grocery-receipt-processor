from __future__ import annotations

from receipt_processor.schemas import MeasureUnit, UnitType

_CANONICAL_UNITS: dict[str, tuple[MeasureUnit, UnitType]] = {
    "KPL": (MeasureUnit.PIECE, UnitType.PIECE),
    "KG": (MeasureUnit.KG, UnitType.WEIGHT),
    "G": (MeasureUnit.G, UnitType.WEIGHT),
    "L": (MeasureUnit.L, UnitType.VOLUME),
    "ML": (MeasureUnit.ML, UnitType.VOLUME),
    "PKT": (MeasureUnit.PACK, UnitType.PACK),
}


def canonicalize_unit(raw_measure_unit: str) -> tuple[MeasureUnit, UnitType]:
    if not raw_measure_unit:
        return MeasureUnit.UNKNOWN, UnitType.UNKNOWN
    key = raw_measure_unit.strip().upper()
    if key not in _CANONICAL_UNITS:
        return MeasureUnit.UNKNOWN, UnitType.UNKNOWN
    return _CANONICAL_UNITS[key]
