"""Minimal, targeted logging configuration for this application's own
loggers (the "app" namespace - app.errors, app.ai.tools, and any future
app.* logger). Deliberately scoped to that one namespace, not the root
logger: it must never touch uvicorn's own access/error logging or any
third-party library's logger, and it must not create duplicate output if
called more than once (safe to call from tests or a reload).

Without this, every `logging.getLogger("app...")` call in the codebase
creates real LogRecords that go nowhere in a running process - Python's
logging module only prints WARNING+ by default when no handler is
configured (the "handler of last resort"), silently dropping every INFO
record such as the AI tool-call audit trail (app.ai.tools.registry).
"""

import logging

from app.core.request_id import get_request_id

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Every attribute a plain LogRecord carries by default - used to detect
# which attributes on a given record were added via `extra={...}` at the
# call site (e.g. tool_name, user_id, duration_ms), so they can be rendered
# generically for ANY app.* logger without hardcoding field names into the
# format string (which would KeyError on a record that doesn't have them).
_STANDARD_LOGRECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))


class _WithExtrasFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Computed BEFORE super().format(): that call mutates the record,
        # adding its own `asctime`/`message` attributes as a side effect,
        # which would otherwise get misidentified as caller-supplied extras.
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOGRECORD_ATTRS and not key.startswith("_")
        }
        base = super().format(record)
        if not extras:
            return base
        rendered = " ".join(f"{key}={value}" for key, value in sorted(extras.items()))
        return f"{base} | {rendered}"


class _RequestIdFilter(logging.Filter):
    """Stamps the current request's correlation id onto every app.* record,
    so no call site has to remember to pass it. Records logged outside a
    request (startup, a background job) simply carry no request_id, rather
    than a misleading placeholder.

    A filter rather than a formatter change: the extras renderer above picks
    it up automatically, and anything that swaps the handler's formatter
    still gets the id."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = get_request_id()
        if request_id is not None:
            record.request_id = request_id
        return True


def configure_app_logging(level: int = logging.INFO) -> None:
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_WithExtrasFormatter(_FORMAT))
        handler.addFilter(_RequestIdFilter())
        app_logger.addHandler(handler)
