"""Tests for app/modules/ai/jobs.py.

The job runner is tested with FakeAnalyzer so no network is ever used.
"""

import uuid

import pytest

from app.modules.ai import jobs
from app.modules.ai.adapter import FakeAnalyzer
from app.modules.ai.jobs import (
    MAX_ATTEMPTS,
    JobInput,
    _failed_result,
    _run_analyzer,
    default_analyzer,
)
from app.modules.ai.service import PROMPT_VERSION


def _make_job() -> JobInput:
    return JobInput(
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        redacted_messages=["Customer: [REDACTED] asks for a demo"],
        pii_values=["Ayesha"],
    )


# ── default_analyzer delegates to the adapter ────────────────────────────────


def test_default_analyzer_uses_fake_adapter(monkeypatch):
    """default_analyzer routes through get_adapter(); FakeAnalyzer is returned
    when LLM_PROVIDER=fake in a non-production environment."""
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("APP_ENV", "development")

    result = default_analyzer(_make_job())

    assert result.status == "ok"
    assert result.model == FakeAnalyzer.MODEL
    assert result.prompt_version == PROMPT_VERSION


def test_default_analyzer_fails_closed_when_provider_raises(monkeypatch):
    """If get_adapter() raises (e.g. bad provider name), _run_analyzer wraps it
    as a failed result when called through process_event, but default_analyzer
    itself propagates the error (it is a wiring mistake, not a provider error)."""
    monkeypatch.setenv("LLM_PROVIDER", "bad_provider_xyz")
    monkeypatch.setenv("APP_ENV", "development")

    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        default_analyzer(_make_job())


# ── _run_analyzer ─────────────────────────────────────────────────────────────


def test_run_analyzer_with_fake_succeeds():
    result = _run_analyzer(FakeAnalyzer(), _make_job())
    assert result.status == "ok"


def test_run_analyzer_captures_provider_exception_as_failed():
    def _bad(_job):
        raise RuntimeError("network gone")

    result = _run_analyzer(_bad, _make_job())
    assert result.status == "failed"


def test_run_analyzer_does_not_catch_not_implemented():
    def _wiring_mistake(_job):
        raise NotImplementedError("adapter not wired")

    with pytest.raises(NotImplementedError):
        _run_analyzer(_wiring_mistake, _make_job())


# ── _failed_result ────────────────────────────────────────────────────────────


def test_failed_result_has_expected_shape():
    r = _failed_result()
    assert r.status == "failed"
    assert r.model == "unavailable"
    assert r.output == {}
    assert r.prompt_version == PROMPT_VERSION


# ── process_event (in-memory session stubs) ───────────────────────────────────


class _FakeSession:
    """Minimal session stub: records calls, never touches a DB."""

    def __init__(self):
        self.executed = []
        self.committed = 0

    def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        return _FakeRows([])

    def commit(self):
        self.committed += 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar(self):
        return None

    def first(self):
        return self._rows[0] if self._rows else None


def _stub_factory(session: _FakeSession):
    def _make():
        return session

    return _make


def test_process_event_skips_when_target_not_found(monkeypatch):
    """When _load returns None (lead deleted), the event is marked processed."""
    session = _FakeSession()

    def _load_none(_db, _event):
        return None

    monkeypatch.setattr(jobs, "_load", _load_none)

    event = jobs.ClaimedEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        event_type="lead.created",
        aggregate_id=uuid.uuid4(),
        attempts=1,
    )
    outcome = jobs.process_event(_stub_factory(session), event, FakeAnalyzer())
    assert outcome == "skipped"


def test_process_event_ok_with_fake_analyzer(monkeypatch):
    """Happy path: _load returns data, FakeAnalyzer returns ok, event processed."""
    session = _FakeSession()
    job = _make_job()

    monkeypatch.setattr(
        jobs,
        "_load",
        lambda _db, _event: jobs._Loaded(job=job, already_assessed=False),
    )
    monkeypatch.setattr(jobs, "_persist_and_mark", lambda *_: None)

    event = jobs.ClaimedEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        event_type="lead.created",
        aggregate_id=job.lead_id,
        attempts=1,
    )
    outcome = jobs.process_event(_stub_factory(session), event, FakeAnalyzer())
    assert outcome == "ok"


def test_process_event_goes_dead_after_max_attempts(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(jobs, "_finish", lambda *_: None)

    event = jobs.ClaimedEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        event_type="lead.created",
        aggregate_id=uuid.uuid4(),
        attempts=MAX_ATTEMPTS + 1,
    )
    outcome = jobs.process_event(_stub_factory(session), event, FakeAnalyzer())
    assert outcome == "dead"
