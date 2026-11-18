#!/usr/bin/env python3
"""simulate_whatsapp.py - Posts a signed WhatsApp inbound webhook message.

Enables demo lead generation and inbound testing without a live Meta setup.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid


def build_whatsapp_inbound_payload(
    *,
    phone_number_id: str,
    sender_phone: str,
    sender_name: str,
    message_text: str,
    waba_id: str = "waba_demo_12345",
    message_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    msg_id = message_id or f"wamid.{uuid.uuid4().hex[:16]}"
    ts = timestamp or str(int(time.time()))

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": waba_id,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550255555",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": sender_name},
                                    "wa_id": sender_phone.lstrip("+"),
                                }
                            ],
                            "messages": [
                                {
                                    "from": sender_phone.lstrip("+"),
                                    "id": msg_id,
                                    "timestamp": ts,
                                    "text": {"body": message_text},
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def post_inbound_message(
    url: str,
    secret: str,
    *,
    phone_number_id: str,
    sender_phone: str,
    sender_name: str,
    message_text: str,
) -> dict:
    payload = build_whatsapp_inbound_payload(
        phone_number_id=phone_number_id,
        sender_phone=sender_phone,
        sender_name=sender_name,
        message_text=message_text,
    )
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
        "User-Agent": "facebookplatform/1.0 (+http://developers.facebook.com)",
    }

    req = urllib.request.Request(
        url,
        data=raw_body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
            return {
                "status_code": resp.status,
                "data": json.loads(content.decode("utf-8")) if content else {},
            }
    except urllib.error.HTTPError as err:
        err_content = err.read().decode("utf-8")
        try:
            parsed = json.loads(err_content)
        except Exception:
            parsed = {"raw": err_content}
        return {"status_code": err.code, "error": parsed}


def main():
    parser = argparse.ArgumentParser(description="Simulate signed WhatsApp inbound webhook message")
    parser.add_argument(
        "--url",
        default=os.environ.get(
            "WHATSAPP_WEBHOOK_URL",
            "http://localhost:8000/api/v1/webhooks/whatsapp",
        ),
        help="Target webhook endpoint",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("META_APP_SECRET", "test-meta-app-secret"),
        help="META_APP_SECRET for signature verification",
    )
    parser.add_argument(
        "--phone-number-id",
        default=os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "phone_number_id_demo"),
        help="Meta phone_number_id configured for integration",
    )
    parser.add_argument(
        "--sender",
        default="+8801700000001",
        help="Sender phone number in E.164 format",
    )
    parser.add_argument(
        "--name",
        default="Ayesha Rahman",
        help="Sender contact name",
    )
    parser.add_argument(
        "--message",
        default="Hi, I would like to learn more about your sales CRM plans for our team.",
        help="Inbound message text",
    )

    args = parser.parse_args()

    print(f"[*] Posting simulated WhatsApp inbound message to {args.url}...")
    print(f"    From: {args.name} ({args.sender})")
    print(f'    Message: "{args.message}"')

    res = post_inbound_message(
        url=args.url,
        secret=args.secret,
        phone_number_id=args.phone_number_id,
        sender_phone=args.sender,
        sender_name=args.name,
        message_text=args.message,
    )
    print(f"[+] Response status: {res.get('status_code')}")
    print(f"    Body: {res.get('data') or res.get('error')}")


if __name__ == "__main__":
    main()
