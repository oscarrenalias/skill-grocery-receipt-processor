from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from receipt_processor.config import ConfigError, load_settings
from receipt_processor.db import create_engine_and_init, get_latest_receipt_dump, get_receipt_dump_by_id
from receipt_processor.errors import error_payload
from receipt_processor.pipeline import process_receipt


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        payload = error_payload("INVALID_ARGUMENTS", message)
        print(json.dumps(payload, ensure_ascii=True))
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Process Finnish grocery receipt PDFs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process_parser = subparsers.add_parser("process", help="Process a receipt PDF")
    process_parser.add_argument("--input", required=True, dest="input_path", help="Path to a receipt PDF")
    process_parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist parsed receipt and items to local SQLite DB",
    )
    process_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode and verbose diagnostic behavior",
    )
    process_parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to also write structured JSON output",
    )

    show_parser = subparsers.add_parser("show", help="Show a persisted receipt by rid or latest")
    show_selector = show_parser.add_mutually_exclusive_group(required=True)
    show_selector.add_argument("--rid", help="Receipt ID to fetch")
    show_selector.add_argument(
        "--latest",
        action="store_true",
        help="Fetch the latest persisted receipt by transaction date/time",
    )
    show_parser.add_argument(
        "--include-raw-text",
        action="store_true",
        help="Include stored raw_text in output payload",
    )
    show_parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to also write structured JSON output",
    )
    show_parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
        help="Output format for show command (default: text)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "process":
        try:
            settings = load_settings()
        except ConfigError as exc:
            payload = error_payload("CONFIG_ERROR", str(exc))
            _emit_json(payload, args.output_path)
            raise SystemExit(2)

        payload = process_receipt(
            input_path=args.input_path,
            persist=args.persist,
            debug=args.debug,
            settings=settings,
        )
        _emit_json(payload, args.output_path)
    elif args.command == "show":
        load_dotenv()
        db_path = os.getenv("RECEIPT_DB_PATH", "./data/receipts.sqlite")
        try:
            engine = create_engine_and_init(db_path)
            if args.latest:
                payload = get_latest_receipt_dump(
                    engine,
                    include_raw_text=args.include_raw_text,
                )
                if payload is None:
                    payload = error_payload("NOT_FOUND", "No persisted receipts found")
            else:
                payload = get_receipt_dump_by_id(
                    engine,
                    args.rid,
                    include_raw_text=args.include_raw_text,
                )
                if payload is None:
                    payload = error_payload("NOT_FOUND", f"Receipt not found for rid={args.rid}")
        except Exception as exc:
            payload = error_payload("DB_READ_FAILED", f"Failed to read receipt: {exc}")
        if payload.get("status") == "error" or args.output_format == "json":
            _emit_json(payload, args.output_path)
        else:
            _emit_text(_render_show_text(payload), args.output_path)
    else:  # pragma: no cover
        payload = error_payload("INVALID_ARGUMENTS", "Unknown command")
        _emit_json(payload, args.output_path)

    if payload.get("status") == "error":
        raise SystemExit(1)


def _emit_json(payload: dict, output_path: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=True)
    print(text)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{text}\n", encoding="utf-8")


def _emit_text(text: str, output_path: str | None) -> None:
    print(text)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{text}\n", encoding="utf-8")


def _render_show_text(payload: dict) -> str:
    receipt = payload.get("receipt", {})
    lines = [
        "Receipt",
        f"Receipt ID: {payload.get('rid', '')}",
        f"Store: {receipt.get('store', '')}",
        f"Address: {receipt.get('addr', '')}",
        f"Transaction Date: {receipt.get('tx_date', '')}",
        f"Transaction Time: {receipt.get('tx_time', '')}",
        f"Currency: {receipt.get('cur', '')}",
        f"Total: {_fmt_money(receipt.get('total'))}",
        "",
        "Items",
    ]

    item_headers = ["Item (Finnish)", "Unit", "Quantity", "Unit Price", "Line Total"]
    items = payload.get("items", [])
    item_rows: list[list[str]] = []
    if not items:
        item_rows.append(["(no items)", "", "", "", ""])
    else:
        for item in items:
            fi_name = item.get("fi", "") or item.get("fi_raw", "") or item.get("raw", "")
            uom = item.get("uom", "") or item.get("raw_uom", "")
            qty = _fmt_number(item.get("qty"))
            unit_price = _fmt_money(item.get("unit_price"))
            line_total = _fmt_money(item.get("line_total"))
            item_rows.append([fi_name, uom, qty, unit_price, line_total])
    lines.extend(_render_ascii_table(item_headers, item_rows))

    adjustments = payload.get("adj", [])
    if adjustments:
        adj_headers = ["Type", "Amount", "Item Index", "Raw"]
        adj_rows: list[list[str]] = []
        for adj in adjustments:
            item_idx = "" if adj.get("item_idx") is None else str(adj.get("item_idx"))
            adj_rows.append([str(adj.get("type", "")), _fmt_money(adj.get("amt")), item_idx, str(adj.get("raw", ""))])
        lines.extend(["", "Adjustments"])
        lines.extend(_render_ascii_table(adj_headers, adj_rows))

    if "raw_text" in payload:
        lines.extend(["", "Raw Text", payload.get("raw_text", "")])

    return "\n".join(lines)


def _fmt_number(value: object) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_money(value: object) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _render_ascii_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    normalized_rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in normalized_rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _line(values: list[str]) -> str:
        cells = [values[i].ljust(widths[i]) for i in range(len(values))]
        return f"| {' | '.join(cells)} |"

    border = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    table_lines = [border, _line(headers), border]
    for row in normalized_rows:
        table_lines.append(_line(row))
    table_lines.append(border)
    return table_lines


if __name__ == "__main__":
    main()
