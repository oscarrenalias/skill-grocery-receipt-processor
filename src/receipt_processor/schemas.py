from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class UnitType(str, Enum):
    PIECE = "piece"
    WEIGHT = "weight"
    VOLUME = "volume"
    PACK = "pack"
    UNKNOWN = "unknown"


class MeasureUnit(str, Enum):
    PIECE = "piece"
    KG = "kg"
    G = "g"
    L = "l"
    ML = "ml"
    PACK = "pack"
    UNKNOWN = "unknown"


class LoyaltyDiscountType(str, Enum):
    PLUSSA = "PLUSSA"
    OMA_PLUSSA = "OMA_PLUSSA"
    KAMPANJA = "KAMPANJA"
    TASAERA = "TASAERA"
    NONE = "NONE"


class ReceiptData(BaseModel):
    store: str = ""
    addr: str = ""
    tx_date: str = ""
    tx_time: str = ""
    tx_ref: str = ""
    cur: str = "EUR"
    loy_total: float = 0.0
    pay_total: float = 0.0
    total: float = 0.0
    tax: str = ""
    conf: float = 0.0


class ReceiptItem(BaseModel):
    raw: str = ""
    fi_raw: str = ""
    fi: str = ""
    en: str = ""
    c1: str = "other"
    c2: str = "unknown"
    c3: str = "uncategorized"
    cpath: str = "other > unknown > uncategorized"
    qty: float = 0.0
    utype: UnitType = UnitType.UNKNOWN
    raw_uom: str = "unknown"
    uom: MeasureUnit = MeasureUnit.UNKNOWN
    uom_qty: float = 0.0
    unit_price: float = 0.0
    line_total: float = 0.0
    loy_disc: float = 0.0
    loyalty_type: LoyaltyDiscountType = LoyaltyDiscountType.NONE
    is_weighted: bool = False
    is_return: bool = False
    conf: float = 0.0
    notes: str = ""


class ReceiptAdjustment(BaseModel):
    type: str = ""
    raw: str = ""
    amt: float = 0.0
    item_idx: int | None = None


class LLMParseResult(BaseModel):
    receipt: ReceiptData
    items: list[ReceiptItem] = Field(default_factory=list)
    adj: list[ReceiptAdjustment] = Field(default_factory=list)
    unparsed: list[str] = Field(default_factory=list)
    warn: list[str] = Field(default_factory=list)


class ProcessSuccess(BaseModel):
    status: Literal["ok", "partial", "duplicate"]
    rid: str
    store: str
    tx_date: str
    total: float
    n_items: int
    n_adj: int
    dup_match: Literal["doc_hash", "text_hash"] | None = None
    warn: list[str] = Field(default_factory=list)


class ProcessError(BaseModel):
    status: Literal["error"]
    err: str
    msg: str
    receipt: dict | None = None
    items: list[dict] = Field(default_factory=list)
    adj: list[dict] = Field(default_factory=list)
    warn: list[str] = Field(default_factory=list)


class ProcessInput(BaseModel):
    input_path: str
    persist: bool = False
    debug: bool = False


def compact_dump(model: BaseModel) -> dict:
    return model.model_dump(
        mode="json",
        exclude_defaults=True,
        exclude_none=True,
        exclude_unset=True,
    )
