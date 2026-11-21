from sqlalchemy import create_engine, text

e = create_engine('postgresql+psycopg://crm_owner:TKlagbetk@db:5432/crm')
with e.connect() as conn:
    conn.execute(text(
        "UPDATE users SET mfa_enabled=false, mfa_secret_encrypted=NULL "
        "WHERE email IN ('admin@acme.test', 'admin@globex.test')"
    ))
    conn.execute(text(
        "DELETE FROM mfa_recovery_codes WHERE user_id IN "
        "(SELECT id FROM users WHERE email IN ('admin@acme.test', 'admin@globex.test'))"
    ))
    conn.commit()
print('MFA reset done')
