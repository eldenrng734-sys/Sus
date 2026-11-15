# SUS User Guide

This guide describes the behavior implemented in the repository. The frontend is incomplete, and several backend capabilities are available only through the API. Use `http://localhost:8000/docs` to inspect the running API's current request and response schemas.

## Current access and navigation

Tenant membership roles are:

- **Rep** (`rep`)
- **Manager** (`manager`)
- **Company Admin** (`admin`)

Platform administration is a separate `is_platform_admin` user flag, not a tenant membership role. A company admin is not automatically a platform admin.

The available frontend routes include login, signup, invitation acceptance, and limited lead screens. There is no general dashboard or complete navigation menu; some pages must be opened directly. The root page is still the Next.js starter page.

| Screen | Availability and limitations |
| --- | --- |
| Login and signup | Present. Login does not provide tenant selection, and signup does not automatically send verification email. |
| Invitation acceptance | Present. The invite token is returned by the invitation API; invitation email delivery is not implemented. |
| Lead list | Present but its current API call is double-prefixed by the shared API helper, so the list request does not match the backend route. |
| Lead creation | Present but the form omits the backend-required `Idempotency-Key` header. The create action is not reliably usable through this screen. |
| Lead details | A detail screen exists; access is still enforced by the backend's tenant and role scope. |
| MFA and tenant selection | The backend has MFA and tenant-context requirements, but the corresponding frontend flow is incomplete. |

Use the API documentation for supported operations. Tenant-scoped API requests require an authenticated user and the applicable tenant context (including `X-Tenant-ID`); never use a tenant identifier as a substitute for authorization.

## Account access and login

### New company

Signup creates a tenant and its initial company admin. The backend requires email verification as part of the authentication flow, but signup does not send the verification email automatically. Check the API docs for the available verification endpoints and configure the local email service as described in the [Setup Guide](SETUP_GUIDE.md).

### Invited user

An admin creates an invitation through the API. The invitation API returns a token; the backend does not send an invitation email. Deliver the token only through an approved, secure channel. The recipient can use the invitation-acceptance screen and then sign in.

### Signing in

1. Open the login screen or use the API login operation shown in `/docs`.
2. Provide the account credentials.
3. Complete any required verification or MFA steps supported by the backend.
4. For tenant-scoped API operations, send the tenant context required by the API.

Admin login requires MFA at the backend. The login UI does not currently connect the complete MFA setup and verification screens. The frontend also does not provide a complete tenant-selection flow, so an existing user's tenant context may need to be obtained through the organization's supported process.

## Rep

### What a Rep can do

The backend scopes a Rep to leads assigned to that user. Within that scope, a Rep can:

- List and view assigned leads through the API.
- View permitted lead details, timeline, and conversations.
- Update permitted lead fields and add lead notes.
- Create a lead through the backend; the backend assigns Rep-created leads according to its ownership rules.
- Submit an outbound message record for a permitted conversation.
- Read AI assessments for leads they are authorized to access.

### Lead and conversation workflow

1. Open a lead from an available screen, or retrieve it through the API.
2. Review the lead details and its conversation/timeline.
3. Update supported lead information or add a note.
4. Use the message API to create an outbound message record if needed.

**Important:** The current lead list screen has a route-prefix issue, and the lead creation form omits the required `Idempotency-Key`. Use the API docs for the supported lead operations rather than assuming these UI actions will succeed.

An outbound message request is persisted with status `queued`. This repository does not send that message through Meta, WhatsApp, or another provider. Do not treat a queued record as a delivered reply.

### Tasks, notifications, and AI

- There is no Rep task list or task-management screen/API.
- There is an internal API that persists rep notifications, but there is no user-facing notification inbox or read API.
- A Rep can read assessments attached to accessible leads. Assessment output is advisory; it does not itself send messages or perform CRM actions.
- The conversation-analysis API can generate a summary and sentiment for an accessible conversation when the provider is configured. This is separate from the assessment/review flow.
- Managers and Company Admins have the assessment review capability. A Rep cannot approve or reject an assessment through the implemented review API.

## Manager

### What a Manager can do

The backend scopes a Manager to their team. Within that scope, a Manager can:

- View team leads and their permitted details, conversations, and timelines.
- Update permitted lead information and add notes.
- Assign leads and run the supported CSV lead import.
- Read assessments for accessible leads and review them through the assessment API.
- List teams within the applicable tenant/data scope.

Managers do not have the Company Admin-only team creation/rename or user-invitation/membership controls.

### Team monitoring limitations

There is no manager dashboard, performance reporting screen, task-monitoring API, or task-management UI in the current repository. Team-level lead visibility is available through the scoped API, but do not assume there are charts, aggregate performance metrics, or task queues.

## Company Admin

### What a Company Admin can do

A Company Admin has tenant-wide data scope and can:

- View and manage tenant leads through the APIs, including assignment and CSV import.
- Create and rename teams.
- Create invitations and manage tenant memberships using the admin-protected membership operations.
- Read and review AI assessments for tenant leads.
- Use the other tenant-scoped operations available in `/docs`.

The API defines invite membership roles as `rep`, `manager`, and `admin`. Review the live OpenAPI schemas for the exact fields and allowed transitions before changing membership.

### Company-level limitations

The repository does not implement a company dashboard, integration-connection/settings screen, lead workflow configuration UI, or general company settings screen. Provider webhooks are inbound endpoints, not a self-service integration setup workflow. There is no task-management interface. Admin MFA is enforced by the backend, but its complete frontend flow is not connected.

## Platform Admin

Platform administration is represented by a separate user flag and an authorization dependency. No platform-administration route or user interface is currently registered in the application. Therefore, this repository does not provide an implemented workflow for platform-wide tenant/company administration, support access, or platform health management.

A Platform Admin should not use Company Admin operations as a substitute for a platform-admin feature. Do not infer platform-wide access from a tenant role.

## Common workflows

### Create or manage a lead

- Use the lead operations in `/docs` to create, retrieve, update, assign, and import leads.
- Lead creation requires an `Idempotency-Key` header. Follow the documented request schema and use the same key when retrying the same logical operation.
- Reps are subject to assigned-lead scope; Managers are scoped to their team; Company Admins are scoped to their tenant.
- The frontend lead list/create screens have the limitations described above.

### Invite a user

1. A Company Admin calls the invitation operation shown in `/docs`.
2. Deliver the returned invitation token through a secure, approved channel. No invitation email is sent by this application.
3. The recipient accepts the invitation and signs in.
4. Verify the membership role and tenant context before using tenant-scoped operations.

### Review an AI assessment

1. Retrieve the lead and its assessments through the API.
2. Check the assessment's `needs_human_review` value and the available assessment details.
3. A Manager or Company Admin may use the review operation exposed in `/docs`.
4. Do not treat an AI recommendation as an action already performed by the system.

### Process a customer message

Incoming provider messages are handled through the configured webhook routes. Reps and other authorized tenant users can access conversations within their lead scope. Creating an outbound message via the API only queues a database record; provider delivery is not implemented here.

## Errors and safe handling

- **Authentication error:** Confirm the account credentials and any required verification/MFA steps.
- **Tenant or permission error:** Confirm the signed-in user is an active member of the requested tenant and has access to the lead/team. Do not retry by changing tenant IDs until access is granted.
- **Validation or conflict error:** Compare the request with the current schema in `/docs`. For lead creation, include the required idempotency header; do not blindly retry a write with a different key.
- **Provider or AI error:** Check the backend's sanitized error response and server-side logs. Never include API keys, auth tokens, full message histories, or sensitive customer data in shared reports.
- **Queued message:** `queued` means persisted for future processing, not delivered.

## Security best practices

- Use only your own account and authorized tenant.
- Protect passwords, verification/invitation links, MFA codes, access tokens, and provider credentials.
- Never share or guess another tenant's ID to probe for data.
- Do not paste customer message histories or secrets into external tools, tickets, or logs.
- Use the API's tenant and role authorization; a UI restriction is not a security boundary.
- Use local/test databases only for development and never use production data for test setup.
- Treat AI assessments as advisory and follow the system's human-review state.

## Frequently asked questions

### Where is the dashboard?

There is no implemented dashboard API or dashboard UI. The root page remains the Next.js starter page.

### Where are my tasks or notifications?

The repository does not provide a task list/management API or user-facing notification inbox. Some backend flows can create task records, and the internal notification endpoint can persist notifications, but neither has a corresponding user workflow.

### Why didn't an outbound message reach the customer?

The message API persists an outbound record as `queued`; no provider delivery worker is implemented in this repository.

### Why did signup or admin login stop before opening the CRM?

Email verification is part of the authentication flow, and admins must complete MFA. Signup does not automatically send verification email, and the frontend does not connect the full MFA flow. Check `/docs` and contact the project administrator for the supported account-verification process.

### Where can I configure Meta, WhatsApp, or n8n?

There is no self-service integration setup screen or n8n workflow in this repository. Do not enter credentials into the browser or send them through chat. Integration configuration must be handled through the project's approved deployment process.
