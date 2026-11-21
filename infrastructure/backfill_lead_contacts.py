from sqlalchemy import create_engine, text
from app.modules.leads.capture_normalize import extract_message_phone, extract_message_email

DATABASE_URL = "postgresql+psycopg://crm_owner:TKlagbetk@db:5432/crm"

def backfill():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        leads = conn.execute(text(
            "SELECT id, tenant_id, name, email, phone FROM leads "
            "WHERE email IS NULL OR phone IS NULL"
        )).fetchall()

        print(f"Found {len(leads)} leads with missing contact details.")
        updated_count = 0

        for lead in leads:
            lead_id, tenant_id, name, email, phone = lead
            new_phone = phone
            new_email = email

            messages = conn.execute(text(
                "SELECT m.message_text FROM messages m "
                "JOIN conversations c ON m.conversation_id = c.id "
                "WHERE c.lead_id = :lead_id AND m.direction = 'inbound' "
                "ORDER BY m.created_at ASC"
            ), {"lead_id": lead_id}).fetchall()

            for (msg_text,) in messages:
                if not msg_text:
                    continue
                if not new_phone:
                    detected_phone = extract_message_phone(msg_text)
                    if detected_phone:
                        new_phone = detected_phone
                        print(f"Extracted phone {new_phone} for lead {name} ({lead_id}) from message: {msg_text!r}")
                if not new_email:
                    detected_email = extract_message_email(msg_text)
                    if detected_email:
                        new_email = detected_email
                        print(f"Extracted email {new_email} for lead {name} ({lead_id}) from message: {msg_text!r}")

            if new_phone != phone or new_email != email:
                conn.execute(text(
                    "UPDATE leads SET phone = :phone, email = :email, version = version + 1 "
                    "WHERE id = :lead_id"
                ), {"phone": new_phone, "email": new_email, "lead_id": lead_id})
                updated_count += 1

        conn.commit()
        print(f"Backfill complete! Updated {updated_count} lead(s).")

if __name__ == "__main__":
    backfill()
