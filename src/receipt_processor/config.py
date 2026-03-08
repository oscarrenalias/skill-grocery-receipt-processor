from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_base_url: str | None
    db_path: str
    default_currency: str
    parser_model: str
    enrich_model: str
    timeout_seconds: int


class ConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer for {name}: {raw}") from exc


def load_settings() -> Settings:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigError("Missing required environment variable OPENAI_API_KEY")

    return Settings(
        openai_api_key=api_key,
        openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
        db_path=os.getenv("RECEIPT_DB_PATH", "./data/receipts.sqlite"),
        default_currency=os.getenv("RECEIPT_DEFAULT_CURRENCY", "EUR"),
        parser_model=os.getenv("RECEIPT_PARSER_MODEL", "o3"),
        enrich_model=os.getenv("RECEIPT_ENRICH_MODEL", "gpt-4.1"),
        timeout_seconds=_as_int("RECEIPT_TIMEOUT_SECONDS", 90),
    )
