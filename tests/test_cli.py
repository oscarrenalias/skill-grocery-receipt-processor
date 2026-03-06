import sys

import pytest

from receipt_processor import cli
from receipt_processor.cli import build_parser


def test_cli_requires_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_cli_process_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["process", "--input", "a.pdf", "--persist", "--debug", "--output", "out.json"])
    assert args.command == "process"
    assert args.input_path == "a.pdf"
    assert args.persist is True
    assert args.debug is True
    assert args.output_path == "out.json"


def test_cli_show_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["show-receipt", "--rid", "abc-123", "--include-raw-text", "--output", "out.json"])
    assert args.command == "show-receipt"
    assert args.rid == "abc-123"
    assert args.latest is False
    assert args.output_format == "text"
    assert args.include_raw_text is True
    assert args.output_path == "out.json"


def test_cli_show_latest_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["show-receipt", "--latest", "--include-raw-text", "--output", "out.json"])
    assert args.command == "show-receipt"
    assert args.latest is True
    assert args.rid is None
    assert args.output_format == "text"
    assert args.include_raw_text is True
    assert args.output_path == "out.json"


def test_cli_show_parses_json_format() -> None:
    parser = build_parser()
    args = parser.parse_args(["show-receipt", "--rid", "abc-123", "--format", "json"])
    assert args.command == "show-receipt"
    assert args.output_format == "json"


def test_cli_show_parses_markdown_format() -> None:
    parser = build_parser()
    args = parser.parse_args(["show-receipt", "--rid", "abc-123", "--format", "markdown"])
    assert args.command == "show-receipt"
    assert args.output_format == "markdown"


def test_cli_show_rejects_invalid_format() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show-receipt", "--rid", "abc-123", "--format", "yaml"])


def test_cli_show_requires_selector() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show-receipt"])


def test_cli_show_disallows_mixed_selectors() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show-receipt", "--rid", "abc-123", "--latest"])


def test_cli_list_receipts_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["list-receipts", "--month", "2026-02", "--output", "out.txt", "--format", "json"])
    assert args.command == "list-receipts"
    assert args.month == "2026-02"
    assert args.output_path == "out.txt"
    assert args.output_format == "json"


def test_cli_list_receipts_parses_markdown_format() -> None:
    parser = build_parser()
    args = parser.parse_args(["list-receipts", "--format", "markdown"])
    assert args.command == "list-receipts"
    assert args.output_format == "markdown"


def test_cli_list_receipts_accepts_slash_month() -> None:
    parser = build_parser()
    args = parser.parse_args(["list-receipts", "--month", "02/2026"])
    assert args.command == "list-receipts"
    assert args.month == "2026-02"


def test_cli_list_receipts_rejects_invalid_month() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["list-receipts", "--month", "2026-13"])


def test_cli_sql_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["sql", "--query", "SELECT rid FROM receipts", "--output", "out.json"])
    assert args.command == "sql"
    assert args.query == "SELECT rid FROM receipts"
    assert args.output_path == "out.json"


def test_cli_schema_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["schema", "--output", "out.json"])
    assert args.command == "schema"
    assert args.output_path == "out.json"


def test_cli_describe_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["describe", "receipts", "--output", "out.json"])
    assert args.command == "describe"
    assert args.table == "receipts"
    assert args.output_path == "out.json"


def test_cli_sample_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["sample", "receipts", "--limit", "10", "--output", "out.json"])
    assert args.command == "sample"
    assert args.table == "receipts"
    assert args.limit == 10
    assert args.output_path == "out.json"


def test_cli_main_show_text_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "get_receipt_dump_by_id",
        lambda *args, **kwargs: {
            "status": "ok",
            "rid": "abc-123",
            "receipt": {
                "store": "K-Citymarket",
                "addr": "Main Street 1",
                "tx_date": "2026-03-01",
                "tx_time": "10:01",
                "cur": "EUR",
                "total": 5.4,
            },
            "items": [
                {
                    "fi": "maito",
                    "uom": "piece",
                    "qty": 2,
                    "unit_price": 1.7,
                    "line_total": 3.4,
                }
            ],
            "adj": [],
        },
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "show-receipt", "--rid", "abc-123"])

    cli.main()
    out = capsys.readouterr().out
    assert "Receipt\n" in out
    assert "Address: Main Street 1" in out
    assert "| Item (Finnish) | Unit  | Quantity | Unit Price | Line Total |" in out
    assert "| maito          | piece | 2        | 1.70       | 3.40       |" in out
    assert "+----------------+-------+----------+------------+------------+" in out
    assert not out.lstrip().startswith("{")


def test_cli_main_show_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "get_receipt_dump_by_id",
        lambda *args, **kwargs: {
            "status": "ok",
            "rid": "abc-123",
            "receipt": {"store": "K-Citymarket", "addr": "", "tx_date": "2026-03-01", "tx_time": "10:01", "cur": "EUR", "total": 5.4},
            "items": [],
            "adj": [],
        },
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "show-receipt", "--rid", "abc-123", "--format", "json"])

    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"status": "ok"' in out


def test_cli_main_show_markdown_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "get_receipt_dump_by_id",
        lambda *args, **kwargs: {
            "status": "ok",
            "rid": "abc-123",
            "receipt": {
                "store": "K-City<market>",
                "addr": "Main & Street",
                "tx_date": "2026-03-01",
                "tx_time": "10:01",
                "cur": "EUR",
                "total": 5.4,
            },
            "items": [
                {
                    "fi": "maito & kerma",
                    "uom": "piece",
                    "qty": 2,
                    "unit_price": 1.7,
                    "line_total": 3.4,
                }
            ],
            "adj": [{"type": "disc", "amt": -0.5, "item_idx": 0, "raw": "promo <5%>"}],
            "raw_text": "A&B <raw>",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["receipt-processor", "show-receipt", "--rid", "abc-123", "--format", "markdown", "--include-raw-text"],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "*🧾 Receipt*" in out
    assert "*📍 Address:* Main & Street" in out
    assert "K-City<market>" in out
    assert "maito & kerma" in out
    assert "*💸 Adjustments*" in out
    assert "```" in out
    assert "A&B <raw>" in out
    assert not out.lstrip().startswith("{")


def test_cli_main_show_error_always_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(cli, "get_receipt_dump_by_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "show-receipt", "--rid", "missing", "--format", "text"])

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1

    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"status": "error"' in out
    assert '"err": "NOT_FOUND"' in out


def test_cli_main_list_receipts_text_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(cli, "_current_month", lambda: "2026-03")
    monkeypatch.setattr(
        cli,
        "list_receipt_summaries_by_month",
        lambda *_args, **_kwargs: [
            {
                "rid": "abc-123",
                "tx_date": "2026-03-01",
                "tx_time": "10:01",
                "store": "K-Citymarket",
                "cur": "EUR",
                "total": 5.4,
                "status": "ok",
                "created_at": "2026-03-06T12:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "list-receipts"])

    cli.main()
    out = capsys.readouterr().out
    assert "Receipts (2026-03)" in out
    assert "Count: 1" in out
    assert "abc-123" in out
    assert "K-Citymarket" in out
    assert not out.lstrip().startswith("{")


def test_cli_main_list_receipts_json_output_with_explicit_month(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "list_receipt_summaries_by_month",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["receipt-processor", "list-receipts", "--month", "2026-02", "--format", "json"],
    )

    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"status": "ok"' in out
    assert '"month": "2026-02"' in out
    assert '"count": 0' in out


def test_cli_main_list_receipts_markdown_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(cli, "_current_month", lambda: "2026-03")
    monkeypatch.setattr(
        cli,
        "list_receipt_summaries_by_month",
        lambda *_args, **_kwargs: [
            {
                "rid": "abc-123",
                "tx_date": "2026-03-01",
                "tx_time": "10:01",
                "store": "K-City<market>",
                "cur": "EUR",
                "total": 5.4,
                "status": "ok",
                "created_at": "2026-03-06T12:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "list-receipts", "--format", "markdown"])

    cli.main()
    out = capsys.readouterr().out
    assert "*🧾 Receipts*" in out
    assert "*📅 Month:* `2026-03`" in out
    assert "K-City<market>" in out
    assert "abc-123" in out
    assert not out.lstrip().startswith("{")


def test_cli_main_sql_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "execute_readonly_sql",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "columns": ["rid"],
            "rows": [["abc-123"]],
            "meta": {"row_count": 1, "truncated": False, "limit_applied": 5000, "execution_ms": 1},
        },
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "sql", "--query", "SELECT rid FROM receipts"])

    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"columns": ["rid"]' in out


def test_cli_main_schema_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "get_schema_summary",
        lambda *_args, **_kwargs: {"status": "ok", "tables": [{"name": "receipts", "columns": []}]},
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "schema"])

    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"tables"' in out


def test_cli_main_describe_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "describe_table",
        lambda *_args, **_kwargs: {"status": "ok", "table": {"name": "receipts", "columns": []}},
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "describe", "receipts"])

    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"table"' in out


def test_cli_main_sample_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(
        cli,
        "sample_table",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "columns": ["rid"],
            "rows": [["abc-123"]],
            "meta": {"row_count": 1, "truncated": False, "limit_applied": 5, "execution_ms": 1},
        },
    )
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "sample", "receipts"])

    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"rows"' in out
