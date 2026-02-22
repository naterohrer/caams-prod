"""
Logging configuration for CAAMS.

Both loggers propagate to the root logger so systemd's journal continues to
capture all output via stdout when running as a service.

Both log files rotate at 10 MB × 5 backups

Call configure_logging() once at application startup (done in main.py).
Then import the named loggers anywhere:
    import logging
    app_logger = logging.getLogger("caams.app")
"""
#logs/access.log - http logging
#logs/app.log - app logs/sytem errors/auth

import logging
import logging.handlers
from pathlib import Path

# Written relative to the project root (one level up from this file).
_DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"

MAX_BYTES    = 10 * 1024 * 1024   # 10 MB per file before rotation
BACKUP_COUNT = 5                   # keep 5 rotated copies → max 50 MB per log

# ── Log formats ───────────────────────────────────────────────────────────────
# access.log:  2026-02-19 12:34:56 | 10.0.0.1 | POST /auth/login | 200 | 45ms
# app.log:     2026-02-19 12:34:56 | WARNING  | caams.auth | LOGIN failed | ...
_ACCESS_FMT = "%(asctime)s | %(message)s"
_APP_FMT    = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT   = "%Y-%m-%d %H:%M:%S"


def configure_logging(log_dir: Path | None = None) -> None:
    """
    Set up rotating file handlers for the access and application loggers.
    Safe to call multiple times — handlers are only added once.
    """
    d = log_dir or _DEFAULT_LOG_DIR
    d.mkdir(parents=True, exist_ok=True)

    _setup_logger(
        name="caams.access",
        log_file=d / "access.log",
        fmt=_ACCESS_FMT,
    )
    _setup_logger(
        name="caams.app",
        log_file=d / "app.log",
        fmt=_APP_FMT,
    )

    # Silence uvicorn's built-in access logger — our ASGI middleware replaces
    # it with better-formatted, timed entries in access.log.
    _silence("uvicorn.access")


def _setup_logger(name: str, log_file: Path, fmt: str) -> None:
    logger = logging.getLogger(name)
    if logger.handlers:
        return  # already configured (e.g. called twice in tests)

    logger.setLevel(logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(fmt, datefmt=_DATE_FMT))
    logger.addHandler(handler)
    logger.propagate = True   # still flows to stdout → journal


def _silence(logger_name: str) -> None:
    """Remove all handlers from a logger and stop propagation."""
    lg = logging.getLogger(logger_name)
    lg.handlers.clear()
    lg.propagate = False
