import logging

from app.core.logging import _WithExtrasFormatter, configure_app_logging


def _make_record(msg: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.ai.tools",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_renders_extra_fields() -> None:
    formatter = _WithExtrasFormatter("%(message)s")
    record = _make_record("ai_tool_call_succeeded", tool_name="get_account_balances", ok=True)
    output = formatter.format(record)
    assert "ai_tool_call_succeeded" in output
    assert "tool_name=get_account_balances" in output
    assert "ok=True" in output


def test_formatter_never_duplicates_standard_attributes() -> None:
    formatter = _WithExtrasFormatter("%(asctime)s %(message)s")
    record = _make_record("plain message")
    output = formatter.format(record)
    # "message=" and "asctime=" must never appear as extras - they are the
    # base formatter's own fields, not caller-supplied `extra=` values.
    assert output.count("message=") == 0
    assert output.count("asctime=") == 0


def test_formatter_omits_separator_when_no_extras() -> None:
    formatter = _WithExtrasFormatter("%(message)s")
    record = _make_record("plain message")
    assert formatter.format(record) == "plain message"


def test_configure_app_logging_is_idempotent() -> None:
    configure_app_logging()
    configure_app_logging()
    app_logger = logging.getLogger("app")
    assert len(app_logger.handlers) == 1
