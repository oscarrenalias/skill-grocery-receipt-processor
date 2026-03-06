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
    args = parser.parse_args(["show", "--rid", "abc-123", "--include-raw-text", "--output", "out.json"])
    assert args.command == "show"
    assert args.rid == "abc-123"
    assert args.latest is False
    assert args.output_format == "text"
    assert args.include_raw_text is True
    assert args.output_path == "out.json"


def test_cli_show_latest_parses_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["show", "--latest", "--include-raw-text", "--output", "out.json"])
    assert args.command == "show"
    assert args.latest is True
    assert args.rid is None
    assert args.output_format == "text"
    assert args.include_raw_text is True
    assert args.output_path == "out.json"


def test_cli_show_parses_json_format() -> None:
    parser = build_parser()
    args = parser.parse_args(["show", "--rid", "abc-123", "--format", "json"])
    assert args.command == "show"
    assert args.output_format == "json"


def test_cli_show_parses_telegram_format() -> None:
    parser = build_parser()
    args = parser.parse_args(["show", "--rid", "abc-123", "--format", "telegram"])
    assert args.command == "show"
    assert args.output_format == "telegram"


def test_cli_show_rejects_invalid_format() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show", "--rid", "abc-123", "--format", "yaml"])


def test_cli_show_requires_selector() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show"])


def test_cli_show_disallows_mixed_selectors() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show", "--rid", "abc-123", "--latest"])


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
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "show", "--rid", "abc-123"])

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
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "show", "--rid", "abc-123", "--format", "json"])

    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"status": "ok"' in out


def test_cli_main_show_telegram_output(monkeypatch, capsys) -> None:
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
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "show", "--rid", "abc-123", "--format", "telegram", "--include-raw-text"])

    cli.main()
    out = capsys.readouterr().out
    assert "<b>Receipt</b>" in out
    assert "<b>Address:</b> Main &amp; Street" in out
    assert "K-City&lt;market&gt;" in out
    assert "maito &amp; kerma" in out
    assert "<b>Adjustments</b>" in out
    assert "<pre>A&amp;B &lt;raw&gt;</pre>" in out
    assert not out.lstrip().startswith("{")


def test_cli_main_show_error_always_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "create_engine_and_init", lambda _: object())
    monkeypatch.setattr(cli, "get_receipt_dump_by_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["receipt-processor", "show", "--rid", "missing", "--format", "text"])

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1

    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    assert '"status": "error"' in out
    assert '"err": "NOT_FOUND"' in out
