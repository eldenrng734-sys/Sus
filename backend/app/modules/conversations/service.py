import uuid
from collections.abc import Sequence

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import apply_data_scope
from app.core.tenancy import TenantContext
from app.database.session import set_tenant_context
from app.modules.ai.models import LeadAssessment
from app.modules.ai.provider import AIProviderError, analyze_with_openai
from app.modules.ai.service import (
    PROMPT_VERSION,
    build_assessment_prompt,
    persist_assessment,
)
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation, Message
from app.modules.conversations.schemas import (
    ConversationAnalysisOut,
    ConversationCreate,
    ConversationOut,
    MessageOut,
    TimelineEvent,
)
from app.modules.leads.models import Interaction, Lead


def _get_lead(session: Session, context: TenantContext, lead_id: uuid.UUID) -> Lead:
    """A lead the caller is allowed to see. 404 (not 403) so existence is not leaked."""
    stmt = apply_data_scope(select(Lead).where(Lead.id == lead_id), Lead, context)
    lead = session.scalars(stmt).first()
    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")
    return lead


def _conversation_query(context: TenantContext):
    """Conversations the caller may see. Access follows the lead's scope
    (rep -> own leads, manager -> own team, admin -> all)."""
    stmt = select(Conversation).join(
        Lead,
        and_(Lead.tenant_id == Conversation.tenant_id, Lead.id == Conversation.lead_id),
    )
    return apply_data_scope(stmt, Lead, context)


def _get_conversation(
    session: Session, context: TenantContext, conversation_id: uuid.UUID
) -> Conversation:
    stmt = _conversation_query(context).where(Conversation.id == conversation_id)
    conversation = session.scalars(stmt).first()
    if conversation is None:
        raise AuthError(404, "not_found", "Conversation not found")
    return conversation


def create_conversation(
    session: Session, context: TenantContext, body: ConversationCreate
) -> ConversationOut:
    lead = _get_lead(session, context, body.lead_id)
    conversation = Conversation(
        tenant_id=context.tenant_id,
        lead_id=lead.id,
        channel=body.channel,
        external_conversation_id=body.external_conversation_id,
        assigned_user_id=lead.assigned_user_id,
    )
    session.add(conversation)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise AuthError(409, "conflict", "This conversation already exists") from None

    # timeline entry
    session.add(
        Interaction(
            tenant_id=context.tenant_id,
            lead_id=lead.id,
            type="conversation_started",
            source=body.channel,
            details={"conversation_id": str(conversation.id)},
        )
    )
    session.flush()
    session.refresh(conversation)
    out = ConversationOut.model_validate(conversation)  # build BEFORE commit
    session.commit()
    return out


def list_conversations(
    session: Session,
    context: TenantContext,
    lead_id: uuid.UUID | None,
    status: str | None,
    limit: int,
    offset: int,
) -> list[ConversationOut]:
    stmt = _conversation_query(context)
    if lead_id:
        stmt = stmt.where(Conversation.lead_id == lead_id)
    if status:
        stmt = stmt.where(Conversation.status == status)
    stmt = (
        stmt.order_by(
            Conversation.last_message_at.desc().nulls_last(),
            Conversation.created_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return [ConversationOut.model_validate(c) for c in session.scalars(stmt)]


def list_messages(
    session: Session,
    context: TenantContext,
    conversation_id: uuid.UUID,
    limit: int,
    offset: int,
) -> list[MessageOut]:
    _get_conversation(session, context, conversation_id)  # permission check
    stmt = (
        select(Message)
        .where(
            Message.tenant_id == context.tenant_id,
            Message.conversation_id == conversation_id,
        )
        .order_by(Message.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return [MessageOut.model_validate(m) for m in session.scalars(stmt)]


def get_timeline(
    session: Session,
    context: TenantContext,
    lead_id: uuid.UUID,
    limit: int,
    offset: int,
) -> list[TimelineEvent]:
    _get_lead(session, context, lead_id)  # permission check
    fetch = limit + offset

    interactions = session.scalars(
        select(Interaction)
        .where(Interaction.tenant_id == context.tenant_id, Interaction.lead_id == lead_id)
        .order_by(Interaction.occurred_at.desc())
        .limit(fetch)
    ).all()

    messages = session.execute(
        select(Message, Conversation.channel)
        .join(
            Conversation,
            and_(
                Conversation.tenant_id == Message.tenant_id,
                Conversation.id == Message.conversation_id,
            ),
        )
        .where(Message.tenant_id == context.tenant_id, Conversation.lead_id == lead_id)
        .order_by(Message.created_at.desc())
        .limit(fetch)
    ).all()

    interaction_types = {
        "note": "note_added",
        "status_change": "status_changed",
        "assignment": "assigned",
        "assigned": "assigned",
        "conversation_started": "integration_event",
    }
    events = [
        TimelineEvent(
            kind="interaction",
            type=interaction_types.get(i.type, i.type),
            at=i.occurred_at,
            summary=i.source,
            details=i.details,
        )
        for i in interactions
    ]
    for message, channel in messages:
        events.append(
            TimelineEvent(
                kind="message",
                type="message_received" if message.direction == "inbound" else "message_sent",
                at=message.created_at,
                summary=(message.message_text or "")[:100],
                details={
                    "conversation_id": str(message.conversation_id),
                    "channel": channel,
                    "status": message.status,
                },
            )
        )
    events.sort(key=lambda e: e.at, reverse=True)
    return events[offset : offset + limit]


def _bounded_conversation(messages: Sequence[str]) -> list[str]:
    """Keep the newest messages within provider input limits."""
    bounded: list[str] = []
    total_chars = 0
    for message in reversed(messages):
        if not message:
            continue
        message = message[-4000:]
        remaining = 20_000 - total_chars
        if remaining <= 0:
            break
        if len(message) > remaining:
            message = message[-remaining:]
        bounded.append(message)
        total_chars += len(message)
        if len(bounded) == 100:
            break
    return list(reversed(bounded))


def analyze_conversation(
    session: Session,
    context: TenantContext,
    conversation_id: uuid.UUID,
) -> ConversationAnalysisOut:
    conversation = _get_conversation(session, context, conversation_id)
    lead = _get_lead(session, context, conversation.lead_id)

    messages = list(
        session.scalars(
            select(Message)
            .where(
                Message.tenant_id == context.tenant_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.desc())
            .limit(100)
        )
    )
    messages.reverse()
    has_customer_message = any(
        message.direction == "inbound" and message.message_text for message in messages
    )
    if not has_customer_message:
        raise AuthError(422, "validation_error", "Conversation has no inbound messages")
    conversation_messages = [
        f"{'Customer' if message.direction == 'inbound' else 'Agent'}: {message.message_text}"
        for message in messages
        if message.direction in {"inbound", "outbound"} and message.message_text
    ]

    configured_key = settings.openai_api_key
    api_key = configured_key.get_secret_value() if configured_key is not None else ""
    if not api_key.strip():
        raise AuthError(503, "service_unavailable", "Conversation analysis is not configured")

    pii_values = [
        value
        for value in (
            lead.name,
            lead.email,
            lead.phone,
            getattr(lead, "company_name", None),
        )
        if value
    ]
    prompt = build_assessment_prompt(
        _bounded_conversation(conversation_messages),
        pii_values=pii_values,
    )

    session.commit()
    model = settings.openai_model
    try:
        output = analyze_with_openai(
            prompt,
            api_key=api_key,
            model=model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    except AIProviderError as exc:
        set_tenant_context(session, str(context.tenant_id))
        persist_assessment(
            session,
            tenant_id=context.tenant_id,
            lead_id=lead.id,
            conversation_id=conversation.id,
            output={},
            model=model,
            prompt_version=PROMPT_VERSION,
            pii_values=pii_values,
            status="failed",
        )
        session.commit()
        raise AuthError(502, "provider_error", "Conversation analysis failed") from exc

    set_tenant_context(session, str(context.tenant_id))
    assessment = persist_assessment(
        session,
        tenant_id=context.tenant_id,
        lead_id=lead.id,
        conversation_id=conversation.id,
        output=output,
        model=model,
        prompt_version=prompt["prompt_version"],
        pii_values=pii_values,
    )
    session.commit()
    return ConversationAnalysisOut.model_validate(assessment)


def get_conversation_analysis(
    session: Session,
    context: TenantContext,
    conversation_id: uuid.UUID,
) -> ConversationAnalysisOut:
    _get_conversation(session, context, conversation_id)
    assessment = session.scalar(
        select(LeadAssessment)
        .where(
            LeadAssessment.tenant_id == context.tenant_id,
            LeadAssessment.conversation_id == conversation_id,
        )
        .order_by(LeadAssessment.created_at.desc())
        .limit(1)
    )
    if assessment is None:
        raise AuthError(404, "not_found", "Conversation analysis not found")
    return ConversationAnalysisOut.model_validate(assessment)
