"""AI worker process entrypoint.

Usage:
    python -m app.worker

Connects to the database using WORKER_DATABASE_URL (the crm_worker role)
and runs the AI assessment job loop until interrupted.

The adapter is selected by LLM_PROVIDER (default: anthropic).
LLM_PROVIDER=fake is accepted in non-production environments only.

This module must NOT be imported from main.py or any HTTP path.
"""

from __future__ import annotations

import logging
import signal
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.database.registry  # noqa: F401
from app.core.config import settings
from app.modules.ai.adapter import get_adapter
from app.modules.ai.jobs import run_forever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app.worker")


def _session_factory(engine):
    def _make() -> Session:
        return Session(engine)

    return _make


def main() -> None:
    db_url = settings.worker_database_url or settings.database_url
    if not db_url:
        logger.error("worker_startup_failed reason=no_database_url")
        sys.exit(1)

    try:
        adapter = get_adapter()
    except (RuntimeError, ValueError) as exc:
        logger.error("worker_startup_failed reason=bad_adapter error=%s", exc)
        sys.exit(1)

    logger.info(
        "worker_starting adapter=%s db=%s",
        type(adapter).__name__,
        db_url.split("@")[-1],  # host/db only — never log credentials
    )

    engine = create_engine(db_url, pool_pre_ping=True)
    factory = _session_factory(engine)

    # Graceful shutdown on SIGTERM / SIGINT.
    _stop = False

    def _handle_signal(sig, _frame):
        nonlocal _stop
        logger.info("worker_stopping signal=%s", sig)
        _stop = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    run_forever(factory, adapter, should_stop=lambda: _stop)
    logger.info("worker_stopped")
    engine.dispose()


if __name__ == "__main__":
    main()
