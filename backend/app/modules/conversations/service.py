import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import apply_data_scope
from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation, Message
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
    TimelineEvent,
)
from app.modules.leads.models import Interaction, Lead
from app.modules.leads.optout import can_message

# messages.provider only allows these two (see the DB check constraint)
MESSAGE_CHANNELS = ("whatsapp", "messenger")


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


def send_message(session: Session, context: TenantContext, body: MessageCreate) -> MessageOut:
    """Store an outbound message as 'queued'. Real sending is added on Day 7."""
    conversation = _get_conversation(session, context, body.conversation_id)
    if conversation.channel not in MESSAGE_CHANNELS:
        raise AuthError(
            422, "validation_error", "Messages are only supported on WhatsApp and Messenger"
        )
    lead = _get_lead(session, context, conversation.lead_id)
    allowed, reason = can_message(lead)
    if not allowed:
        if reason == "opt_out":
            raise AuthError(403, "opt_out", "This lead has opted out of messages")
        raise AuthError(403, "no_consent", "This lead has not consented to messages")

    message = Message(
        tenant_id=context.tenant_id,
        conversation_id=conversation.id,
        provider=conversation.channel,
        direction="outbound",
        message_text=body.message_text,
        status="queued",
    )
    session.add(message)
    conversation.last_message_at = datetime.now(UTC)
    session.flush()
    session.refresh(message)
    out = MessageOut.model_validate(message)  # build BEFORE commit
    session.commit()
    return out


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
