import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.modules.ai.service import ConversationAnalysisOutput
from app.modules.auth.errors import AuthError
from app.modules.conversations import service


def test_analyze_conversation_redacts_pii_persists_and_returns_analysis(monkeypatch):
    tenant_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    context = SimpleNamespace(tenant_id=tenant_id)
    conversation = SimpleNamespace(id=conversation_id, lead_id=lead_id)
    lead = SimpleNamespace(
        id=lead_id,
        name="Ayesha Rahman",
        email="ayesha@example.com",
        phone="+1 415 555 0199",
    )
    messages = [
        SimpleNamespace(
            direction="inbound",
            message_text="Can we have a demo? Call me at 415-555-0199",
        ),
        SimpleNamespace(direction="outbound", message_text="Sure Ayesha, I will arrange it."),
    ]
    session = MagicMock()
    session.scalars.return_value.__iter__.return_value = list(reversed(messages))
    monkeypatch.setattr(service, "_get_conversation", lambda *args: conversation)
    monkeypatch.setattr(service, "_get_lead", lambda *args: lead)
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "openai_model", "gpt-test")
    prompts = {}

    def analyze(prompt, **kwargs):
        prompts.update(prompt)
        assert kwargs["api_key"] == "test-api-key"
        assert kwargs["model"] == "gpt-test"
        return ConversationAnalysisOutput(
            summary="The customer requested a demo.",
            sentiment="positive",
            confidence=0.9,
        )

    persisted = {}

    def persist(_session, **kwargs):
        persisted.update(kwargs)
        return SimpleNamespace(
            summary=kwargs["output"].summary,
            sentiment=kwargs["output"].sentiment,
            confidence=kwargs["output"].confidence,
            needs_human_review=False,
            status="ok",
            model=kwargs["model"],
            prompt_version=kwargs["prompt_version"],
            created_at=datetime.now(UTC),
        )

    monkeypatch.setattr(service, "analyze_with_openai", analyze)
    monkeypatch.setattr(service, "persist_assessment", persist)

    result = service.analyze_conversation(session, context, conversation_id)

    assert result.summary == "The customer requested a demo."
    assert result.sentiment == "positive"
    assert result.model == "gpt-test"
    assert result.prompt_version == "lead-assessment-v2"
    assert "Ayesha" not in prompts["user"]
    assert "ayesha@example.com" not in prompts["user"]
    assert "415-555-0199" not in prompts["user"]
    assert "Customer:" in prompts["user"]
    assert "Agent:" in prompts["user"]
    assert persisted["tenant_id"] == tenant_id
    assert persisted["lead_id"] == lead_id
    assert persisted["conversation_id"] == conversation_id
    assert persisted["output"].sentiment == "positive"
    assert session.commit.call_count == 2


def test_analyze_conversation_requires_messages(monkeypatch):
    conversation = SimpleNamespace(id=uuid.uuid4(), lead_id=uuid.uuid4())
    lead = SimpleNamespace(id=conversation.lead_id, name="A", email=None, phone=None)
    session = MagicMock()
    session.scalars.return_value.__iter__.return_value = []
    monkeypatch.setattr(service, "_get_conversation", lambda *args: conversation)
    monkeypatch.setattr(service, "_get_lead", lambda *args: lead)

    with pytest.raises(AuthError) as exc:
        service.analyze_conversation(
            session,
            SimpleNamespace(tenant_id=uuid.uuid4()),
            conversation.id,
        )

    assert exc.value.status_code == 422
    assert session.commit.called is False


def test_analyze_conversation_requires_openai_configuration(monkeypatch):
    conversation = SimpleNamespace(id=uuid.uuid4(), lead_id=uuid.uuid4())
    lead = SimpleNamespace(id=conversation.lead_id, name="Ayesha", email=None, phone=None)
    message = SimpleNamespace(direction="inbound", message_text="Need a demo")
    session = MagicMock()
    session.scalars.return_value.__iter__.return_value = [message]
    monkeypatch.setattr(service, "_get_conversation", lambda *args: conversation)
    monkeypatch.setattr(service, "_get_lead", lambda *args: lead)
    monkeypatch.setattr(settings, "openai_api_key", None)

    with pytest.raises(AuthError) as exc:
        service.analyze_conversation(
            session,
            SimpleNamespace(tenant_id=uuid.uuid4()),
            conversation.id,
        )

    assert exc.value.status_code == 503
    assert session.commit.called is False


def test_analyze_conversation_treats_blank_api_key_as_unconfigured(monkeypatch):
    conversation = SimpleNamespace(id=uuid.uuid4(), lead_id=uuid.uuid4())
    lead = SimpleNamespace(id=conversation.lead_id, name="Ayesha", email=None, phone=None)
    message = SimpleNamespace(direction="inbound", message_text="Need a demo")
    session = MagicMock()
    session.scalars.return_value.__iter__.return_value = [message]
    monkeypatch.setattr(service, "_get_conversation", lambda *args: conversation)
    monkeypatch.setattr(service, "_get_lead", lambda *args: lead)
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))

    with pytest.raises(AuthError) as exc:
        service.analyze_conversation(
            session,
            SimpleNamespace(tenant_id=uuid.uuid4()),
            conversation.id,
        )

    assert exc.value.status_code == 503
    assert session.commit.called is False


def test_bounded_conversation_keeps_recent_text_with_limits():
    messages = ["old"] + ["x" * 5000 for _ in range(100)]

    result = service._bounded_conversation(messages)

    assert len(result) <= 100
    assert sum(map(len, result)) <= 20_000
    assert result[-1] == "x" * 4000
