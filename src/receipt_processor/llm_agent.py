from __future__ import annotations

import os

from agents import Agent, ModelSettings, RunConfig, Runner

from receipt_processor.config import Settings
from receipt_processor.schemas import LLMParseResult


class ParseError(RuntimeError):
    """Raised when LLM parsing fails."""


def _build_instructions() -> str:
    return (
        "You parse Finnish grocery receipts into strict structured data using compact keys. "
        "Return JSON that exactly matches the short-key schema from the output type. "
        "Do not invent numeric values. Keep original raw line text. "
        "Extract metadata, line items, discounts, refunds/deposits. "
        "Only product purchase rows belong in items. "
        "Do not emit standalone unit-detail rows like '2 KPL 0,75 EUR/KPL' or '0,234 KG 43,76 EUR/KG' as separate items; treat them as metadata for the closest named item. "
        "Do not emit promo/discount marker rows with no product name as items. Use adjustments for financial impact lines only. "
        "Never double-count: one product purchase must appear once in items. "
        "Units must map to canonical values only: piece,kg,g,l,ml,pack,unknown. "
        "utype must be one of piece,weight,volume,pack,unknown. "
        "Recognize loyalty_type values: PLUSSA, OMA_PLUSSA, KAMPANJA, TASAERA, NONE. "
        "If uncertain, preserve raw and lower conf. "
        "For unsupported units set uom=unknown and utype=unknown."
    )


def parse_receipt_with_llm(
    raw_text: str,
    *,
    settings: Settings,
    debug: bool = False,
) -> LLMParseResult:
    try:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        if settings.openai_base_url:
            os.environ["OPENAI_BASE_URL"] = settings.openai_base_url

        parser_agent = Agent(
            name="finnish_receipt_parser",
            instructions=_build_instructions(),
            model=settings.parser_model,
            # Note: some reasoning models (e.g. o3) reject sampling params like temperature.
            # Keep model settings unset for maximum compatibility unless we add per-model logic.
            output_type=LLMParseResult,
        )

        input_text = (
            "Parse this receipt text and return structured output matching the schema:\n\n"
            f"{raw_text}"
        )

        run_config = RunConfig(tracing_disabled=not debug)
        result = Runner.run_sync(parser_agent, input_text, run_config=run_config)
        parsed = result.final_output_as(LLMParseResult, raise_if_incorrect_type=True)
        return parsed
    except Exception as exc:
        raise ParseError(f"LLM parsing failed: {exc}") from exc
