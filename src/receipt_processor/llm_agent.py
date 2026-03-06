from __future__ import annotations

import os

from agents import Agent, ModelSettings, RunConfig, Runner

from receipt_processor.config import Settings
from receipt_processor.schemas import LLMParseResult
from receipt_processor.taxonomy import ALLOWED_C3


class ParseError(RuntimeError):
    """Raised when LLM parsing fails."""


def _supports_sampling_params(model: str) -> bool:
    normalized = model.strip().lower()
    # Reasoning model families (e.g. o1/o3/o4) reject sampling params.
    return not normalized.startswith(("o1", "o3", "o4"))


def _model_settings_for(model: str) -> ModelSettings | None:
    if _supports_sampling_params(model):
        return ModelSettings(temperature=0, top_p=1.0)
    return None


def _build_instructions() -> str:
    allowed_c3 = ",".join(ALLOWED_C3)
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
        "Classify taxonomy by selecting c3 from this exact allowlist only: "
        f"{allowed_c3}. "
        "If uncertain, set c3=uncategorized. c1/c2/cpath will be derived from c3. "
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

        agent_kwargs = {
            "name": "finnish_receipt_parser",
            "instructions": _build_instructions(),
            "model": settings.parser_model,
            "output_type": LLMParseResult,
        }
        model_settings = _model_settings_for(settings.parser_model)
        if model_settings is not None:
            agent_kwargs["model_settings"] = model_settings

        parser_agent = Agent(
            **agent_kwargs,
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
