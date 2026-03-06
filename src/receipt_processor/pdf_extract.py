from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


class TextExtractionError(RuntimeError):
    """Raised when text extraction from the PDF fails."""


def extract_text_from_pdf(input_path: str) -> str:
    path = Path(input_path)
    if not path.exists() or not path.is_file():
        raise TextExtractionError(f"Input PDF not found: {input_path}")

    try:
        reader = PdfReader(str(path))
        lines: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            lines.extend(_normalize_text_lines(text))
        content = "\n".join(lines).strip()
    except Exception as exc:  # pragma: no cover - pypdf internals
        raise TextExtractionError(f"Failed to read PDF: {exc}") from exc

    if not content:
        raise TextExtractionError("Extracted PDF text is empty")

    return content


def _normalize_text_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw_line in text.splitlines():
        cleaned = " ".join(raw_line.replace("\t", " ").split())
        out.append(cleaned)
    return out
