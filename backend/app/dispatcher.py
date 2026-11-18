"""n8n event dispatcher process entrypoint.

Usage:
    python -m app.dispatcher

Connects to the database using WORKER_DATABASE_URL (the crm_worker role)
and dispatches pending outbox events to the n8n webhook URL with HMAC-SHA256 signatures.

This module must NOT be imported from main.py or any HTTP path.
"""

from __future__ import annotations

import logging
import signal
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dispatcher import run_forever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app.dispatcher")


def _session_factory(engine):
    def _make() -> Session:
        return Session(engine)

    return _make


def main() -> None:
    db_url = settings.worker_database_url or settings.database_url
    if not db_url:
        logger.error("dispatcher_startup_failed reason=no_database_url")
        sys.exit(1)

    webhook_url = settings.n8n_webhook_url
    signing_secret = settings.n8n_event_signing_secret.get_secret_value()

    if not signing_secret:
        logger.warning("dispatcher_startup_warning reason=empty_n8n_event_signing_secret")

    logger.info(
        "dispatcher_starting webhook_url=%s db=%s",
        webhook_url,
        db_url.split("@")[-1],  # host/db only — never log credentials
    )

    engine = create_engine(db_url, pool_pre_ping=True)
    factory = _session_factory(engine)

    _stop = False

    def _handle_signal(sig, _frame):
        nonlocal _stop
        logger.info("dispatcher_stopping signal=%s", sig)
        _stop = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    run_forever(
        factory,
        webhook_url=webhook_url,
        signing_secret=signing_secret,
        poll_seconds=settings.n8n_dispatcher_poll_seconds,
        should_stop=lambda: _stop,
    )
    logger.info("dispatcher_stopped")
    engine.dispose()


if __name__ == "__main__":
    main()
