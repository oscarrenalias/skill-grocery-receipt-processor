from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from receipt_processor.config import ConfigError, load_settings
from receipt_processor.db import (
    create_engine_and_init,
    get_latest_receipt_dump,
    get_receipt_dump_by_id,
    list_receipt_summaries_by_month,
)
from receipt_processor.errors import error_payload
from receipt_processor.pipeline import process_receipt
from receipt_processor.query import describe_table, execute_readonly_sql, get_schema_summary, sample_table


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

    show_parser = subparsers.add_parser("show-receipt", help="Show a persisted receipt by rid or latest")
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
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format for show-receipt command (default: text)",
    )

    list_parser = subparsers.add_parser("list-receipts", help="List persisted receipts for a month")
    list_parser.add_argument(
        "--month",
        type=_parse_month_argument,
        help="Month filter in YYYY-MM (recommended) or MM/YYYY; defaults to current month",
    )
    list_parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to also write structured JSON output",
    )
    list_parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format for list-receipts command (default: text)",
    )

    sql_parser = subparsers.add_parser("sql", help="Run restricted read-only SQL query")
    sql_parser.add_argument("--query", required=True, help="Single SELECT SQL query to execute")
    sql_parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to also write structured JSON output",
    )

    schema_parser = subparsers.add_parser("schema", help="List queryable tables and columns")
    schema_parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to also write structured JSON output",
    )

    describe_parser = subparsers.add_parser("describe", help="Describe a queryable table")
    describe_parser.add_argument("table", help="Table name to describe")
    describe_parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to also write structured JSON output",
    )

    sample_parser = subparsers.add_parser("sample", help="Sample rows from a queryable table")
    sample_parser.add_argument("table", help="Table name to sample")
    sample_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of rows to return (default: 5)",
    )
    sample_parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to also write structured JSON output",
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
    elif args.command == "show-receipt":
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
        _emit_formatted_payload(
            payload,
            output_format=args.output_format,
            output_path=args.output_path,
            text_renderer=_render_show_text,
            markdown_renderer=_render_show_markdown,
        )
    elif args.command == "list-receipts":
        load_dotenv()
        db_path = os.getenv("RECEIPT_DB_PATH", "./data/receipts.sqlite")
        month = args.month or _current_month()
        try:
            engine = create_engine_and_init(db_path)
            receipts_payload = list_receipt_summaries_by_month(engine, month)
            payload = {
                "status": "ok",
                "filter": {"month": month},
                "count": len(receipts_payload),
                "receipts": receipts_payload,
            }
        except Exception as exc:
            payload = error_payload("DB_READ_FAILED", f"Failed to read receipts: {exc}")
        _emit_formatted_payload(
            payload,
            output_format=args.output_format,
            output_path=args.output_path,
            text_renderer=_render_list_receipts_text,
            markdown_renderer=_render_list_receipts_markdown,
        )
    elif args.command == "sql":
        load_dotenv()
        db_path = os.getenv("RECEIPT_DB_PATH", "./data/receipts.sqlite")
        try:
            create_engine_and_init(db_path)
            payload = execute_readonly_sql(db_path, args.query)
        except ValueError as exc:
            payload = error_payload("INVALID_ARGUMENTS", str(exc))
        except Exception as exc:
            payload = error_payload("DB_READ_FAILED", f"Failed to run SQL query: {exc}")
        _emit_json(payload, args.output_path)
    elif args.command == "schema":
        load_dotenv()
        db_path = os.getenv("RECEIPT_DB_PATH", "./data/receipts.sqlite")
        try:
            engine = create_engine_and_init(db_path)
            payload = get_schema_summary(engine)
        except ValueError as exc:
            payload = error_payload("INVALID_ARGUMENTS", str(exc))
        except Exception as exc:
            payload = error_payload("DB_READ_FAILED", f"Failed to load schema: {exc}")
        _emit_json(payload, args.output_path)
    elif args.command == "describe":
        load_dotenv()
        db_path = os.getenv("RECEIPT_DB_PATH", "./data/receipts.sqlite")
        try:
            engine = create_engine_and_init(db_path)
            payload = describe_table(engine, args.table)
        except ValueError as exc:
            payload = error_payload("INVALID_ARGUMENTS", str(exc))
        except Exception as exc:
            payload = error_payload("DB_READ_FAILED", f"Failed to describe table: {exc}")
        _emit_json(payload, args.output_path)
    elif args.command == "sample":
        load_dotenv()
        db_path = os.getenv("RECEIPT_DB_PATH", "./data/receipts.sqlite")
        try:
            create_engine_and_init(db_path)
            payload = sample_table(db_path, args.table, limit=args.limit)
        except ValueError as exc:
            payload = error_payload("INVALID_ARGUMENTS", str(exc))
        except Exception as exc:
            payload = error_payload("DB_READ_FAILED", f"Failed to sample table: {exc}")
        _emit_json(payload, args.output_path)
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


def _emit_formatted_payload(
    payload: dict,
    *,
    output_format: str,
    output_path: str | None,
    text_renderer,
    markdown_renderer,
) -> None:
    if payload.get("status") == "error" or output_format == "json":
        _emit_json(payload, output_path)
    elif output_format == "markdown":
        _emit_text(markdown_renderer(payload), output_path)
    else:
        _emit_text(text_renderer(payload), output_path)


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


def _render_list_receipts_text(payload: dict) -> str:
    month = payload.get("filter", {}).get("month", "")
    receipts_payload = payload.get("receipts", [])
    lines = [
        f"Receipts ({month})",
        f"Count: {payload.get('count', 0)}",
        "",
    ]

    headers = ["Receipt ID", "Transaction Date", "Transaction Time", "Store", "Currency", "Total", "Status"]
    rows: list[list[str]] = []
    if not receipts_payload:
        rows.append(["(no receipts found)", "", "", "", "", "", ""])
    else:
        for receipt in receipts_payload:
            rows.append(
                [
                    str(receipt.get("rid", "")),
                    str(receipt.get("tx_date", "")),
                    str(receipt.get("tx_time", "")),
                    str(receipt.get("store", "")),
                    str(receipt.get("cur", "")),
                    _fmt_money(receipt.get("total")),
                    str(receipt.get("status", "")),
                ]
            )
    lines.extend(_render_ascii_table(headers, rows))
    return "\n".join(lines)


def _render_show_markdown(payload: dict) -> str:
    receipt = payload.get("receipt", {})
    lines = [
        "*🧾 Receipt*",
        f"*🆔 Receipt ID:* `{_md(payload.get('rid'))}`",
        f"*🏬 Store:* {_md(receipt.get('store'))}",
        f"*📍 Address:* {_md(receipt.get('addr'))}",
        f"*📅 Transaction Date:* `{_md(receipt.get('tx_date'))}`",
        f"*⏰ Transaction Time:* `{_md(receipt.get('tx_time'))}`",
        f"*💱 Currency:* `{_md(receipt.get('cur'))}`",
        f"*💰 Total:* `{_md(_fmt_money(receipt.get('total')))}`",
        "",
        "*🛒 Items*",
    ]

    items = payload.get("items", [])
    if not items:
        lines.append("_(no items)_")
    else:
        lines.extend(["```", *_render_receipt_item_lines(items), "```"])

    adjustments = payload.get("adj", [])
    if adjustments:
        lines.extend(["", "*💸 Adjustments*", "```", *_render_receipt_adjustment_lines(adjustments), "```"])

    if "raw_text" in payload:
        lines.extend(["", "*📄 Raw Text*", f"```\n{_md(payload.get('raw_text'))}\n```"])

    return "\n".join(lines)


def _render_list_receipts_markdown(payload: dict) -> str:
    month = payload.get("filter", {}).get("month", "")
    receipts_payload = payload.get("receipts", [])
    lines = [
        "*🧾 Receipts*",
        f"*📅 Month:* `{_md(month)}`",
        f"*🔢 Count:* `{_md(payload.get('count', 0))}`",
        "",
    ]
    if not receipts_payload:
        lines.append("_(no receipts found)_")
        return "\n".join(lines)

    lines.extend(["```", *_render_list_receipts_lines(receipts_payload), "```"])
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


def _render_receipt_item_lines(items: list[dict]) -> list[str]:
    normalized_rows: list[tuple[str, str, str, str, str, str]] = []
    for idx, item in enumerate(items, start=1):
        fi_name = str(item.get("fi", "") or item.get("fi_raw", "") or item.get("raw", ""))
        uom = str(item.get("uom", "") or item.get("raw_uom", ""))
        qty = _fmt_number(item.get("qty"))
        unit_price = _fmt_money(item.get("unit_price"))
        line_total = _fmt_money(item.get("line_total"))
        normalized_rows.append((f"{idx:02d}.", fi_name, uom, qty, unit_price, line_total))

    name_w = max(len(row[1]) for row in normalized_rows)
    uom_w = max(5, max(len(row[2]) for row in normalized_rows))
    qty_w = max(3, max(len(row[3]) for row in normalized_rows))
    money_w = max(4, max(max(len(row[4]), len(row[5])) for row in normalized_rows))

    lines: list[str] = []
    for idx_dot, fi_name, uom, qty, unit_price, line_total in normalized_rows:
        lines.append(
            f"{idx_dot} {fi_name:<{name_w}}  {uom:<{uom_w}}  "
            f"qty {qty:>{qty_w}}  unit {unit_price:>{money_w}}  line {line_total:>{money_w}}"
        )
    return lines


def _render_receipt_adjustment_lines(adjustments: list[dict]) -> list[str]:
    normalized_rows: list[tuple[str, str, str, str]] = []
    for adj in adjustments:
        adj_type = str(adj.get("type", ""))
        amt = _fmt_money(adj.get("amt"))
        item_idx = "-" if adj.get("item_idx") is None else str(adj.get("item_idx"))
        raw = str(adj.get("raw", ""))
        normalized_rows.append((adj_type, amt, item_idx, raw))

    type_w = max(4, max(len(row[0]) for row in normalized_rows))
    amt_w = max(3, max(len(row[1]) for row in normalized_rows))
    idx_w = max(4, max(len(row[2]) for row in normalized_rows))

    return [
        f"type {adj_type:<{type_w}}  amt {amt:>{amt_w}}  item {item_idx:<{idx_w}}  raw {raw}"
        for adj_type, amt, item_idx, raw in normalized_rows
    ]


def _render_list_receipts_lines(receipts_payload: list[dict]) -> list[str]:
    normalized_rows: list[tuple[str, str, str, str, str, str, str]] = []
    for idx, receipt in enumerate(receipts_payload, start=1):
        rid = str(receipt.get("rid", ""))
        tx_date = str(receipt.get("tx_date", ""))
        tx_time = str(receipt.get("tx_time", ""))
        store = str(receipt.get("store", ""))
        cur = str(receipt.get("cur", ""))
        total = _fmt_money(receipt.get("total"))
        status = str(receipt.get("status", ""))
        normalized_rows.append((f"{idx:02d}.", rid, tx_date, tx_time, store, f"{total} {cur}".strip(), status))

    rid_w = max(3, max(len(row[1]) for row in normalized_rows))
    date_w = max(10, max(len(row[2]) for row in normalized_rows))
    time_w = max(5, max(len(row[3]) for row in normalized_rows))
    store_w = max(5, max(len(row[4]) for row in normalized_rows))
    total_w = max(5, max(len(row[5]) for row in normalized_rows))
    status_w = max(6, max(len(row[6]) for row in normalized_rows))

    return [
        f"{idx_dot} {rid:<{rid_w}}  "
        f"{tx_date:<{date_w}} {tx_time:<{time_w}}  "
        f"{store:<{store_w}}  "
        f"total {total_cur:>{total_w}}  "
        f"status {status:<{status_w}}"
        for idx_dot, rid, tx_date, tx_time, store, total_cur, status in normalized_rows
    ]


def _md(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_month_argument(value: str) -> str:
    stripped = value.strip()
    iso_match = re.fullmatch(r"(\d{4})-(\d{2})", stripped)
    if iso_match:
        year, month = iso_match.groups()
        if 1 <= int(month) <= 12:
            return f"{year}-{month}"
        raise argparse.ArgumentTypeError("month must be between 01 and 12")

    slash_match = re.fullmatch(r"(\d{2})/(\d{4})", stripped)
    if slash_match:
        month, year = slash_match.groups()
        if 1 <= int(month) <= 12:
            return f"{year}-{month}"
        raise argparse.ArgumentTypeError("month must be between 01 and 12")

    raise argparse.ArgumentTypeError("invalid month format; use YYYY-MM (recommended) or MM/YYYY")


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


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
