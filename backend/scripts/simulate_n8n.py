#!/usr/bin/env python3
"""simulate_n8n.py - Simulates n8n Workflow A and sub-workflow sign-and-call.

Can be run standalone to:
1. Verify the Golden Vector against core/service_auth.py.
2. Execute the full Workflow A orchestration against a running FastAPI backend.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

GOLDEN_SECRET = "test-golden-service-secret-key-12345"
GOLDEN_SERVICE_ID = "n8n"
GOLDEN_TENANT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
GOLDEN_METHOD = "POST"
GOLDEN_PATH = "/internal/v1/automation/notifications"
GOLDEN_TIMESTAMP = "1700000000"
GOLDEN_IDEMPOTENCY_KEY = "golden-idempotency-key-001"
GOLDEN_RAW_BODY = b'{"type":"new_lead","title":"New lead"}'
GOLDEN_EXPECTED_SIGNATURE = (
    "sha256=f24f7a152e7388f25a0eda7f17e298dfbbc58177ca54a8fa5180c3a603602ef6"
)


def compute_canonical_string(
    *,
    service_id: str = "n8n",
    tenant_id: str,
    method: str,
    path: str,
    timestamp: str,
    idempotency_key: str,
    raw_body: bytes,
) -> bytes:
    body_sha256 = hashlib.sha256(raw_body).hexdigest()
    fields = [
        "v1",
        service_id,
        tenant_id,
        method.upper(),
        path,
        timestamp,
        idempotency_key,
        body_sha256,
    ]
    return "\n".join(fields).encode("utf-8")


def sign_request(
    secret: str,
    *,
    service_id: str = "n8n",
    tenant_id: str,
    method: str,
    path: str,
    idempotency_key: str,
    body: dict | None = None,
    timestamp: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    ts = timestamp or str(int(time.time()))
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else b""
    canonical = compute_canonical_string(
        service_id=service_id,
        tenant_id=tenant_id,
        method=method,
        path=path,
        timestamp=ts,
        idempotency_key=idempotency_key,
        raw_body=raw_body,
    )
    digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    signature = f"sha256={digest}"

    headers = {
        "X-Service-Id": service_id,
        "X-Tenant-ID": tenant_id,
        "X-Timestamp": ts,
        "X-Idempotency-Key": idempotency_key,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }
    return raw_body, headers


def verify_golden_vector() -> bool:
    canonical = compute_canonical_string(
        service_id=GOLDEN_SERVICE_ID,
        tenant_id=GOLDEN_TENANT_ID,
        method=GOLDEN_METHOD,
        path=GOLDEN_PATH,
        timestamp=GOLDEN_TIMESTAMP,
        idempotency_key=GOLDEN_IDEMPOTENCY_KEY,
        raw_body=GOLDEN_RAW_BODY,
    )
    digest = hmac.new(GOLDEN_SECRET.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    sig = f"sha256={digest}"
    matches = sig == GOLDEN_EXPECTED_SIGNATURE
    if matches:
        print("[PASS] Golden vector signature matches exactly:")
        print(f"       {sig}")
    else:
        print("[FAIL] Golden vector mismatch:")
        print(f"       Expected: {GOLDEN_EXPECTED_SIGNATURE}")
        print(f"       Computed: {sig}")
    return matches


def call_internal_api(
    base_url: str,
    secret: str,
    *,
    tenant_id: str,
    method: str,
    path: str,
    idempotency_key: str,
    body: dict | None = None,
) -> dict:
    raw_body, headers = sign_request(
        secret,
        tenant_id=tenant_id,
        method=method,
        path=path,
        idempotency_key=idempotency_key,
        body=body,
    )
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(
        url,
        data=raw_body if method.upper() not in ("GET", "HEAD") else None,
        headers=headers,
        method=method.upper(),
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


def run_workflow_a(
    base_url: str,
    secret: str,
    *,
    tenant_id: str,
    lead_id: str,
    event_id: str | None = None,
) -> dict:
    ev_id = event_id or str(uuid.uuid4())
    print(f"[*] Starting Workflow A for lead {lead_id} (event {ev_id})...")

    # Step 1: Fetch lead context
    print(" -> 1. GET /internal/v1/automation/leads/{lead_id}")
    lead_resp = call_internal_api(
        base_url,
        secret,
        tenant_id=tenant_id,
        method="GET",
        path=f"/internal/v1/automation/leads/{lead_id}",
        idempotency_key=f"{ev_id}-get-lead",
    )
    if lead_resp.get("status_code") != 200:
        print(f" [!] Error fetching lead: {lead_resp}")
        return lead_resp

    lead_data = lead_resp["data"]["data"]
    assigned_user_id = lead_data.get("assigned_user_id")
    lead_name = lead_data.get("name", "Unknown")
    print(f"    Lead Name: {lead_name}, Assigned: {assigned_user_id}")

    # Step 2: Request assessment if needed
    print(" -> 2. POST /internal/v1/automation/leads/{lead_id}/assess")
    assess_resp = call_internal_api(
        base_url,
        secret,
        tenant_id=tenant_id,
        method="POST",
        path=f"/internal/v1/automation/leads/{lead_id}/assess",
        idempotency_key=f"{ev_id}-assess",
        body={},
    )
    print(f"    Assessment status: {assess_resp.get('status_code')}")

    # Step 3: Notify assigned rep if present
    notif_resp = None
    if assigned_user_id:
        print(f" -> 3. POST /internal/v1/automation/notifications for rep {assigned_user_id}")
        notif_resp = call_internal_api(
            base_url,
            secret,
            tenant_id=tenant_id,
            method="POST",
            path="/internal/v1/automation/notifications",
            idempotency_key=ev_id,
            body={
                "user_id": assigned_user_id,
                "type": "new_lead",
                "title": f"New Lead: {lead_name}",
                "body": f"New lead {lead_name} has been assigned to you.",
                "entity_type": "lead",
                "entity_id": lead_id,
            },
        )
        print(f"    Notification status: {notif_resp.get('status_code')}")
    else:
        print(" -> 3. No rep assigned; skipping notification.")

    print("[+] Workflow A simulation completed successfully.")
    return {
        "status": "completed",
        "lead": lead_data,
        "assessment": assess_resp,
        "notification": notif_resp,
    }


def run_workflow_b(
    base_url: str,
    secret: str,
    *,
    tenant_id: str,
    task_id: str,
    event_id: str | None = None,
    retry_count: int = 0,
) -> dict:
    ev_id = event_id or str(uuid.uuid4())
    print(f"[*] Starting Workflow B for task {task_id} (event {ev_id})...")

    # Step 1: POST /internal/v1/automation/messages
    print(f" -> 1. POST /internal/v1/automation/messages for task {task_id}")
    send_resp = call_internal_api(
        base_url,
        secret,
        tenant_id=tenant_id,
        method="POST",
        path="/internal/v1/automation/messages",
        idempotency_key=ev_id,
        body={"task_id": task_id},
    )

    status_code = send_resp.get("status_code", 500)
    err_obj = send_resp.get("error", {})
    err_code = "unknown"
    if isinstance(err_obj, dict):
        nested = err_obj.get("error")
        if isinstance(nested, dict) and "code" in nested:
            err_code = nested["code"]
        elif "code" in err_obj:
            err_code = err_obj["code"]

    outcome = "unknown"
    record_payload = None

    if status_code == 200:
        outcome = "sent"
        msg_id = send_resp.get("data", {}).get("data", {}).get("message_id")
        record_payload = {
            "status": "sent",
            "task_status": "done",
            "message_id": msg_id,
            "note": "Sent automated WhatsApp follow-up.",
        }
    elif status_code == 202:
        outcome = "quiet_hours"
        print("    [!] Quiet hours active: task rescheduled by backend. Nothing to record.")
        return {
            "status": "rescheduled",
            "outcome": "quiet_hours",
            "send_response": send_resp,
        }
    elif err_code == "approval_required":
        outcome = "approval_required"
        record_payload = {
            "status": "needs_approval",
            "error_code": "approval_required",
        }
    elif err_code == "opted_out":
        outcome = "opted_out"
        record_payload = {
            "status": "skipped",
            "task_status": "cancelled",
            "error_code": "opted_out",
            "note": "Lead opted out; follow-up cancelled.",
        }
    elif err_code == "window_closed":
        outcome = "window_closed"
        record_payload = {
            "status": "skipped",
            "error_code": "window_closed",
            "note": "24-hour reply window closed. Manual template required.",
        }
    elif err_code in ("task_not_open", "task_inactive", "lead_closed"):
        outcome = "task_not_open"
        record_payload = {
            "status": "skipped",
            "error_code": err_code,
            "note": f"Task or lead inactive ({err_code}); skipped.",
        }
    else:
        outcome = "failed"
        is_first_failure = retry_count < 1
        record_payload = {
            "status": "failed",
            "retryable": is_first_failure,
            "error_code": err_code,
        }

    # Step 2: Record task result if needed
    result_resp = None
    if record_payload:
        print(f" -> 2. POST /internal/v1/automation/tasks/{task_id}/result (outcome: {outcome})")
        result_resp = call_internal_api(
            base_url,
            secret,
            tenant_id=tenant_id,
            method="POST",
            path=f"/internal/v1/automation/tasks/{task_id}/result",
            idempotency_key=f"{ev_id}-result",
            body=record_payload,
        )
        print(f"    Result recorded: {result_resp.get('status_code')}")

    print(f"[+] Workflow B simulation completed with outcome: {outcome}")
    return {
        "status": "completed",
        "outcome": outcome,
        "send_response": send_resp,
        "result_response": result_resp,
    }


def run_workflow_c(
    base_url: str,
    secret: str,
    *,
    tenant_id: str,
    lead_id: str,
    event_id: str | None = None,
) -> dict:
    ev_id = event_id or str(uuid.uuid4())
    print(f"[*] Starting Workflow C for customer reply on lead {lead_id} (event {ev_id})...")

    # Step 1: Fetch lead context
    print(" -> 1. GET /internal/v1/automation/leads/{lead_id}")
    lead_resp = call_internal_api(
        base_url,
        secret,
        tenant_id=tenant_id,
        method="GET",
        path=f"/internal/v1/automation/leads/{lead_id}",
        idempotency_key=f"{ev_id}-get-lead",
    )
    if lead_resp.get("status_code") != 200:
        print(f" [!] Error fetching lead: {lead_resp}")
        return lead_resp

    lead_data = lead_resp.get("data", {}).get("data", {})
    assigned_user_id = lead_data.get("assigned_user_id")
    lead_name = lead_data.get("name", "Unknown")
    print(f"    Lead Name: {lead_name}, Assigned: {assigned_user_id}")

    # Step 2: Notify assigned rep if present, or managers if unassigned
    notif_resp = None
    manager_user_ids = lead_data.get("manager_user_ids") or []
    if assigned_user_id:
        print(f" -> 2. POST /internal/v1/automation/notifications for rep {assigned_user_id}")
        notif_resp = call_internal_api(
            base_url,
            secret,
            tenant_id=tenant_id,
            method="POST",
            path="/internal/v1/automation/notifications",
            idempotency_key=f"{ev_id}-notif",
            body={
                "user_id": assigned_user_id,
                "type": "new_lead",
                "title": f"Customer Replied: {lead_name}",
                "body": f"Customer {lead_name} replied to your message.",
                "entity_type": "lead",
                "entity_id": lead_id,
            },
        )
        print(f"    Notification status: {notif_resp.get('status_code')}")
    elif manager_user_ids:
        print(
            " -> 2. POST /internal/v1/automation/notifications"
            f" for {len(manager_user_ids)} managers"
        )
        notif_responses = []
        for mgr_id in manager_user_ids:
            resp = call_internal_api(
                base_url,
                secret,
                tenant_id=tenant_id,
                method="POST",
                path="/internal/v1/automation/notifications",
                idempotency_key=f"{ev_id}-notif-{mgr_id}",
                body={
                    "user_id": mgr_id,
                    "type": "new_lead",
                    "title": f"Customer Replied: {lead_name}",
                    "body": f"Unassigned lead {lead_name} replied to message.",
                    "entity_type": "lead",
                    "entity_id": lead_id,
                },
            )
            notif_responses.append(resp)
        notif_resp = notif_responses[0] if notif_responses else None
    else:
        print(" -> 2. Lead has no assigned owner; skipping notification.")

    # Step 3: Request/re-run assessment
    print(" -> 3. POST /internal/v1/automation/leads/{lead_id}/assess")
    assess_resp = call_internal_api(
        base_url,
        secret,
        tenant_id=tenant_id,
        method="POST",
        path=f"/internal/v1/automation/leads/{lead_id}/assess",
        idempotency_key=f"{ev_id}-assess",
        body={},
    )
    print(f"    Assessment status: {assess_resp.get('status_code')}")

    print("[+] Workflow C simulation completed successfully.")
    return {
        "status": "completed",
        "lead": lead_data,
        "notification": notif_resp,
        "assessment": assess_resp,
    }


def main():
    parser = argparse.ArgumentParser(description="Simulate n8n Workflows and HMAC signing")
    parser.add_argument(
        "--workflow",
        choices=["a", "b", "c"],
        default="a",
        help="Workflow to simulate: 'a' (lead.created), 'b' (task.due), or 'c' (lead.replied)",
    )
    parser.add_argument(
        "--verify-vector",
        action="store_true",
        help="Verify the canonical Golden Vector",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BACKEND_URL", "http://localhost:8000"),
        help="FastAPI backend URL",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("SERVICE_HMAC_SECRET", ""),
        help="SERVICE_HMAC_SECRET for internal auth",
    )
    parser.add_argument("--tenant-id", help="Target tenant UUID")
    parser.add_argument("--lead-id", help="Target lead UUID (for Workflow A and C)")
    parser.add_argument("--task-id", help="Target task UUID (for Workflow B)")
    parser.add_argument("--event-id", help="Optional outbox event UUID")

    args = parser.parse_args()

    if args.verify_vector:
        ok = verify_golden_vector()
        sys.exit(0 if ok else 1)

    if not args.secret:
        print("Error: SERVICE_HMAC_SECRET must be set via --secret or env var.")
        sys.exit(1)

    if not args.tenant_id:
        print("Error: --tenant-id is required.")
        sys.exit(1)

    if args.workflow == "a":
        if not args.lead_id:
            print("Error: --lead-id is required for Workflow A.")
            sys.exit(1)
        run_workflow_a(
            base_url=args.base_url,
            secret=args.secret,
            tenant_id=args.tenant_id,
            lead_id=args.lead_id,
            event_id=args.event_id,
        )
    elif args.workflow == "b":
        if not args.task_id:
            print("Error: --task-id is required for Workflow B.")
            sys.exit(1)
        run_workflow_b(
            base_url=args.base_url,
            secret=args.secret,
            tenant_id=args.tenant_id,
            task_id=args.task_id,
            event_id=args.event_id,
        )
    elif args.workflow == "c":
        if not args.lead_id:
            print("Error: --lead-id is required for Workflow C.")
            sys.exit(1)
        run_workflow_c(
            base_url=args.base_url,
            secret=args.secret,
            tenant_id=args.tenant_id,
            lead_id=args.lead_id,
            event_id=args.event_id,
        )


if __name__ == "__main__":
    main()
