"""Background runner that auto-assesses new leads and inbound messages (Day 9).

Place at: backend/app/modules/ai/jobs.py

Flow (ARCHITECTURE.md sections 8 and 14):
  claim outbox rows -> per job: set tenant, load lead + messages, redact PII,
  END the read transaction, call the analyzer (the LLM) with no DB transaction
  open, then persist the assessment and mark the event processed in ONE
  transaction.

Rules this file keeps:
  * tenant context is set (transaction-local) before every tenant query
  * the LLM is never called inside a DB transaction
  * an analyzer/LLM failure becomes a 'failed' assessment flagged for human
    review, so a lead is never lost
  * unexpected errors retry with backoff, then the event goes 'dead'
  * nothing here logs message text or PII (ids and error class names only)

Usage (session_factory is whatever your app uses to open a Session):

    from app.modules.ai.jobs import run_once, run_forever
    run_once(SessionLocal, analyzer=my_analyzer)
"""

from __future__ import annotations

import logging
import os
import socket
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.ai.provider import AIProviderError, analyze_with_openai
from app.modules.ai.service import (
    PROMPT_VERSION,
    build_assessment_prompt,
    persist_assessment,
    redact_pii,
)

logger = logging.getLogger("app.ai.jobs")

HANDLED_EVENTS = ("lead.created", "message.received")
MAX_ATTEMPTS = 5
LEASE_SECONDS = 300  # a 'processing' row older than this is treated as abandoned
BATCH_SIZE = 10
MAX_MESSAGES = 20  # most recent inbound messages sent for assessment
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600

Status = Literal["ok", "fallback", "failed"]
SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class ClaimedEvent:
    id: uuid.UUID
    tenant_id: uuid.UUID
    event_type: str
    aggregate_id: uuid.UUID
    attempts: int


@dataclass(frozen=True)
class JobInput:
    """What an analyzer receives. Messages are ALREADY redacted."""

    tenant_id: uuid.UUID
    lead_id: uuid.UUID
    conversation_id: uuid.UUID | None
    redacted_messages: list[str]
    pii_values: list[str] = field(repr=False)


@dataclass(frozen=True)
class AnalysisResult:
    output: dict  # validated by persist_assessment (AssessmentOutput)
    model: str
    prompt_version: str
    status: Status


Analyzer = Callable[[JobInput], AnalysisResult]


def default_analyzer(job: JobInput) -> AnalysisResult:
    """Run the configured conversation analyzer over the already-redacted input."""
    configured_key = settings.openai_api_key
    api_key = configured_key.get_secret_value() if configured_key is not None else ""
    if not api_key.strip():
        raise AIProviderError("AI conversation analysis is not configured")

    prompt = build_assessment_prompt(job.redacted_messages, pii_values=job.pii_values)
    output = analyze_with_openai(
        prompt,
        api_key=api_key,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    return AnalysisResult(
        output=output.model_dump(),
        model=settings.openai_model,
        prompt_version=prompt["prompt_version"],
        status="ok",
    )


def _failed_result() -> AnalysisResult:
    return AnalysisResult(
        output={},
        model="unavailable",
        prompt_version=PROMPT_VERSION,
        status="failed",
    )


# --------------------------------------------------------------------------- claim

_CLAIM_SQL = text(
    """
    WITH picked AS (
        SELECT id FROM outbox_events
        WHERE event_type = ANY(:types)
          AND (
                (status = 'pending' AND available_at <= now())
             OR (status = 'processing'
                 AND locked_at < now() - make_interval(secs => CAST(:lease AS double precision)))
          )
        ORDER BY available_at, created_at
        LIMIT :n
        FOR UPDATE SKIP LOCKED
    )
    UPDATE outbox_events e
       SET status = 'processing', locked_at = now(), locked_by = :worker,
           attempts = e.attempts + 1
      FROM picked
     WHERE e.id = picked.id
    RETURNING e.id, e.tenant_id, e.event_type, e.aggregate_id, e.attempts
    """
)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def claim_batch(
    session_factory: SessionFactory,
    *,
    limit: int = BATCH_SIZE,
    worker: str | None = None,
) -> list[ClaimedEvent]:
    """Claim a bounded batch in one short transaction.

    This reads across tenants, so the DB role needs the outbox worker-claim RLS
    policy (DATABASE_SCHEMA.md section 13). Business tables are never touched here.
    """
    with session_factory() as db:
        rows = db.execute(
            _CLAIM_SQL,
            {
                "types": list(HANDLED_EVENTS),
                "lease": LEASE_SECONDS,
                "n": limit,
                "worker": worker or worker_id(),
            },
        ).all()
        db.commit()
    return [
        ClaimedEvent(r.id, r.tenant_id, r.event_type, r.aggregate_id, r.attempts)
        for r in rows
    ]


# --------------------------------------------------------------------------- helpers


def _set_tenant(db: Session, tenant_id: uuid.UUID) -> None:
    """Transaction-local tenant context. Must be re-run after every commit."""
    db.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )


def _mark(db: Session, event: ClaimedEvent, status: str, error: str | None) -> None:
    db.execute(
        text(
            """
            UPDATE outbox_events
               SET status = :s, processed_at = now(), last_error = :e,
                   locked_at = NULL, locked_by = NULL
             WHERE id = :id AND tenant_id = :t
            """
        ),
        {"s": status, "e": error, "id": event.id, "t": event.tenant_id},
    )


def _finish(
    session_factory: SessionFactory,
    event: ClaimedEvent,
    status: str,
    error: str | None,
) -> None:
    with session_factory() as db:
        _set_tenant(db, event.tenant_id)
        _mark(db, event, status, error)
        db.commit()


@dataclass(frozen=True)
class _Loaded:
    job: JobInput
    already_assessed: bool


def _load(db: Session, event: ClaimedEvent) -> _Loaded | None:
    """Read everything the job needs. Returns None if the lead or message is gone."""
    t = event.tenant_id
    conversation_id: uuid.UUID | None = None
    since = None

    if event.event_type == "message.received":
        row = db.execute(
            text(
                """
                SELECT c.lead_id, m.conversation_id, m.created_at
                  FROM messages m
                  JOIN conversations c ON c.tenant_id = m.tenant_id AND c.id = m.conversation_id
                 WHERE m.tenant_id = :t AND m.id = :id
                """
            ),
            {"t": t, "id": event.aggregate_id},
        ).first()
        if row is None:
            return None
        lead_id, conversation_id, since = row
    else:
        lead_id = event.aggregate_id

    lead = db.execute(
        text(
            """
            SELECT name, email, phone, company_name, created_at
              FROM leads
             WHERE tenant_id = :t
               AND id = :l
            """
        ),
        {"t": t, "l": lead_id},
    ).first()
    if lead is None:
        return None
    since = since or lead.created_at

    if conversation_id is None:
        conversation_id = db.execute(
            text(
                """
                SELECT id FROM conversations
                 WHERE tenant_id = :t AND lead_id = :l
                 ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"t": t, "l": lead_id},
        ).scalar()

    already = (
        db.execute(
            text(
                """
                SELECT 1 FROM lead_assessments
                 WHERE tenant_id = :t AND lead_id = :l AND created_at >= :since
                 LIMIT 1
                """
            ),
            {"t": t, "l": lead_id, "since": since},
        ).first()
        is not None
    )

    raw_messages = (
        db.execute(
            text(
                """
                SELECT m.message_text
                  FROM messages m
                  JOIN conversations c ON c.tenant_id = m.tenant_id AND c.id = m.conversation_id
                 WHERE m.tenant_id = :t AND c.lead_id = :l
                   AND m.direction = 'inbound' AND m.message_text IS NOT NULL
                 ORDER BY m.created_at DESC
                 LIMIT :n
                """
            ),
            {"t": t, "l": lead_id, "n": MAX_MESSAGES},
        )
        .scalars()
        .all()
    )

    pii_values = [v for v in (lead.name, lead.email, lead.phone, lead.company_name) if v]
    redacted = [redact_pii(m, pii_values) for m in reversed(raw_messages)]
    job = JobInput(
        tenant_id=t,
        lead_id=lead_id,
        conversation_id=conversation_id,
        redacted_messages=redacted,
        pii_values=pii_values,
    )
    return _Loaded(job=job, already_assessed=already)


def _run_analyzer(analyzer: Analyzer, job: JobInput) -> AnalysisResult:
    """Call the analyzer. Any failure becomes a flagged 'failed' assessment."""
    try:
        result = analyzer(job)
    except NotImplementedError:
        raise  # a wiring mistake, not an LLM failure: retry, then dead, never hide it
    except Exception as exc:
        logger.warning(
            "analyzer_failed lead=%s error=%s",
            job.lead_id,
            type(exc).__name__,
        )
        return _failed_result()
    if not isinstance(result, AnalysisResult) or result.status not in (
        "ok",
        "fallback",
        "failed",
    ):
        return _failed_result()
    return result


def _persist_and_mark(
    session_factory: SessionFactory,
    event: ClaimedEvent,
    job: JobInput,
    result: AnalysisResult,
) -> None:
    """Assessment + 'processed' commit together, so a crash cannot leave a duplicate window."""
    with session_factory() as db:
        _set_tenant(db, event.tenant_id)
        persist_assessment(
            db,
            tenant_id=job.tenant_id,
            lead_id=job.lead_id,
            conversation_id=job.conversation_id,
            output=result.output,
            model=result.model,
            prompt_version=result.prompt_version,
            pii_values=job.pii_values,
            status=result.status,
        )
        _mark(db, event, "processed", None)
        db.commit()


def _fail_or_retry(
    session_factory: SessionFactory,
    event: ClaimedEvent,
    exc: Exception,
) -> None:
    code = type(exc).__name__  # class name only: never put message text in last_error
    if event.attempts >= MAX_ATTEMPTS:
        _finish(session_factory, event, "dead", code)
        return
    delay = min(BACKOFF_BASE_SECONDS * 2 ** (event.attempts - 1), BACKOFF_CAP_SECONDS)
    with session_factory() as db:
        _set_tenant(db, event.tenant_id)
        db.execute(
            text(
                """
                UPDATE outbox_events
                   SET status = 'pending', last_error = :e,
                       available_at = now() + make_interval(secs => CAST(:d AS double precision)),
                       locked_at = NULL, locked_by = NULL
                 WHERE id = :id AND tenant_id = :t
                """
            ),
            {"e": code, "d": delay, "id": event.id, "t": event.tenant_id},
        )
        db.commit()


# --------------------------------------------------------------------------- runner


def process_event(
    session_factory: SessionFactory,
    event: ClaimedEvent,
    analyzer: Analyzer = default_analyzer,
) -> str:
    """Handle one claimed event. Returns: ok | fallback | failed | skipped | dead | error."""
    if event.attempts > MAX_ATTEMPTS:  # e.g. a worker that keeps crashing mid-job
        _finish(session_factory, event, "dead", "max_attempts_exceeded")
        return "dead"
    try:
        with session_factory() as db:
            _set_tenant(db, event.tenant_id)
            loaded = _load(db, event)
            db.commit()  # end the read transaction BEFORE the LLM call

        if loaded is None:
            _finish(session_factory, event, "processed", "target_not_found")
            return "skipped"
        if loaded.already_assessed:
            _finish(session_factory, event, "processed", None)
            return "skipped"

        result = _run_analyzer(analyzer, loaded.job)
        try:
            _persist_and_mark(session_factory, event, loaded.job, result)
        except ValueError:  # includes pydantic ValidationError: bad output is never trusted
            logger.warning("invalid_analysis lead=%s", loaded.job.lead_id)
            result = _failed_result()
            _persist_and_mark(session_factory, event, loaded.job, result)
        return result.status
    except Exception as exc:
        logger.warning("job_error event=%s error=%s", event.id, type(exc).__name__)
        try:
            _fail_or_retry(session_factory, event, exc)
        except Exception as inner:  # DB down: the lease will let another run reclaim it
            logger.error(
                "job_retry_failed event=%s error=%s",
                event.id,
                type(inner).__name__,
            )
        return "error"


def run_once(
    session_factory: SessionFactory,
    analyzer: Analyzer = default_analyzer,
    *,
    batch_size: int = BATCH_SIZE,
) -> Counter:
    """Claim one batch and process it. Returns a count of outcomes."""
    outcomes: Counter = Counter()
    for event in claim_batch(session_factory, limit=batch_size):
        outcomes[process_event(session_factory, event, analyzer)] += 1
    return outcomes


def run_forever(
    session_factory: SessionFactory,
    analyzer: Analyzer = default_analyzer,
    *,
    poll_seconds: float = 2.0,
    should_stop: Callable[[], bool] = lambda: False,
) -> None:
    """Simple polling loop for the worker process."""
    while not should_stop():
        try:
            handled = sum(run_once(session_factory, analyzer).values())
        except Exception as exc:
            logger.error("worker_loop_error error=%s", type(exc).__name__)
            handled = 0
        if handled == 0:
            time.sleep(poll_seconds)