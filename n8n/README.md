# n8n Automation Workflows

This directory contains the n8n automation workflows for the AI Sales CRM:
- **Sub-workflow:** `sign-and-call` (HMAC authentication & internal API caller)
- **Workflow A:** `lead.created` orchestrator (assessment check & rep notification)
- **Workflow B:** `task.due` orchestrator (follow-up message dispatcher)
- **Workflow C:** `lead.replied` orchestrator (reply pause handler)

---

## 1. Internal Service Authentication & Golden Vector

All requests from n8n to the FastAPI backend (`http://backend:8000`) are authenticated via HMAC-SHA256 signatures over a canonical request string (see `app/core/service_auth.py`).

### Canonical Request Format (v1)

```text
v1
SERVICE_ID
TENANT_ID
METHOD
PATH
TIMESTAMP
IDEMPOTENCY_KEY
SHA256(raw_body)
```
- Joined with a single newline (`\n`, UTF-8).
- `SERVICE_ID`: `n8n`
- `METHOD`: uppercase (e.g., `GET`, `POST`)
- `TIMESTAMP`: decimal Unix epoch seconds
- `SHA256(raw_body)`: lowercase hex-digest of request body bytes (empty string hash if no body)
- Signature header: `X-Signature: sha256=<64 lowercase hex characters>` computed as `HMAC-SHA256(SERVICE_HMAC_SECRET, canonical_bytes)`

### Golden Vector Specification

Both n8n sub-workflow `sign-and-call` and `simulate_n8n.py` must reproduce this exact signature:

```text
SERVICE_HMAC_SECRET: test-golden-service-secret-key-12345
SERVICE_ID:          n8n
TENANT_ID:           a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
METHOD:               POST
PATH:                 /internal/v1/automation/notifications
TIMESTAMP:            1700000000
IDEMPOTENCY_KEY:      golden-idempotency-key-001
RAW_BODY:             {"type":"new_lead","title":"New lead"}

BODY_SHA256:
9636ffd5118576eb56cc29efa63d5f1d184fd6e063cc29cdbefacff8ba77fe19

CANONICAL STRING:
v1
n8n
a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
POST
/internal/v1/automation/notifications
1700000000
golden-idempotency-key-001
9636ffd5118576eb56cc29efa63d5f1d184fd6e063cc29cdbefacff8ba77fe19

EXPECTED SIGNATURE:
sha256=f24f7a152e7388f25a0eda7f17e298dfbbc58177ca54a8fa5180c3a603602ef6
```

Verified in Python via `backend/tests/unit/test_service_auth_vectors.py`.

---

## 2. Secrets & Environment in Code Nodes

Per security guidelines, **no secrets or credentials are ever written into workflow JSON files**.
The n8n container exposes environment variables to Code nodes via:
```yaml
N8N_BLOCK_ENV_ACCESS_IN_NODE: "false"
NODE_FUNCTION_ALLOW_ENV: "SERVICE_HMAC_SECRET,N8N_EVENT_SIGNING_SECRET"
```
In Code nodes:
```javascript
const serviceSecret = $env.SERVICE_HMAC_SECRET;
const signingSecret = $env.N8N_EVENT_SIGNING_SECRET;
```

---

## 3. Workflow A: New Lead (`lead.created`)

Triggered when the backend dispatcher sends a `lead.created` event:
1. Verifies `X-Signature` using `N8N_EVENT_SIGNING_SECRET` over `timestamp + '.' + raw_body`.
2. Validates timestamp is within 300 seconds of server time.
3. Invokes sub-workflow to `GET /internal/v1/automation/leads/{lead_id}`.
4. Checks assessment status: calls `POST /internal/v1/automation/leads/{lead_id}/assess` only if assessment is missing or failed.
5. Invokes sub-workflow to `POST /internal/v1/automation/notifications` for the assigned rep (using the event ID as `X-Idempotency-Key`).
6. **Strict invariant:** Never reassigns the lead and never creates a task or duplicate assessment.
