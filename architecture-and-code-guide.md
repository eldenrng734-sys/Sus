# How Syntrix AI Sales CRM Works: The Complete Beginner-Friendly Guide

Welcome to your project! You have built a **Multi-Tenant AI Sales Assistant CRM**. It is a modern, high-security software application designed to help businesses automatically capture leads from websites and social media, qualify them using artificial intelligence, assign them to sales representatives, and automate compliant follow-ups over WhatsApp and messaging channels.

This document is written for complete beginners. You do not need years of software engineering experience to understand it. We will avoid complicated jargon where simple words work, explain every concept with real-world analogies, and trace real data through your actual files and functions.

---

## Table of Contents
1. [Short Overview: What the Project Is & Simple Flow Diagram](#1-short-overview)
2. [Function-by-Function Map: Who Calls Whom & What Data Moves](#2-function-by-function-map)
3. [Detailed Walkthrough: The Start-to-Finish Story](#3-detailed-walkthrough)
4. [Glossary of Tools and Concepts (Plain English & Analogies)](#4-glossary-of-tools-and-concepts)

---

## 1. Short Overview

### What Is Syntrix CRM in Plain Words?
Imagine a company called **Acme Traders** and another company called **Globex Interiors**. Both sell products, but they are completely separate businesses and competitors.

Instead of each company having to build their own expensive software from scratch, both use **Syntrix CRM**.
- **Multi-Tenant SaaS**: Think of Syntrix like a **modern, luxury office building**. 
  - The building's foundation, elevators, plumbing, and electricity are shared (that is your single database server and backend computer).
  - But **Acme** rents Suite 401 and **Globex** rents Suite 502. 
  - Each suite has an **unpickable electronic deadbolt**. Even if someone from Globex walks through the hallways, they can *never* open Acme's door, read Acme's customer list, or see Acme's revenue numbers. In your code, this deadbolt is called **PostgreSQL Row-Level Security (RLS)**.

### What Does the System Actually Do?
When a prospective customer (a **Lead**) fills out a form on Acme's website or sends a WhatsApp message:
1. **Instant Capture**: The system receives their name, phone number, and question, checking for spam automatically.
2. **AI Analysis**: Instead of a human salesperson spending 30 minutes reading through notes, an **Artificial Intelligence (AI) Concierge** reads the inquiry, figures out if the customer is serious, estimates their buying intent, and recommends what to do next.
3. **Smart Assignment**: The customer is assigned to the right salesperson (a **Sales Rep**) using round-robin distribution so work is split fairly.
4. **Follow-Up Automation**: The system automatically schedules tasks and follow-up messages. If it is the middle of the night in Bangladesh (e.g. 11:00 PM), the system pauses and reschedules the message for 9:00 AM the next morning so the customer is not disturbed (**Quiet Hours**).
5. **Real-Time Workspace**: The sales rep logs into a sleek web dashboard, sees a notification bell light up, reviews the AI's recommendation, and replies directly to the customer over WhatsApp.

---

### Simple Flow Diagram

```text
 ┌────────────────────────────────────────────────────────┐
 │ 1. INCOMING INQUIRY                                    │
 │    Website Visitor / WhatsApp / Facebook Messenger     │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 2. FASTAPI BACKEND INGESTION                           │
 │    • Anti-spam honeypot verification                   │
 │    • Customer deduplication (by phone / email)         │
 │    • Saves to PostgreSQL under strict Tenant Isolation │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 3. GUARANTEED OUTBOX DISPATCHER                        │
 │    • Writes event to "outbox_events" table in same TX  │
 │    • Background dispatcher picks it up & signs HMAC    │
 │    • Dispatches securely to self-hosted n8n engine     │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 4. AI QUALIFICATION & ASSIGNMENT                       │
 │    • LLM Adapter scrubs PII & scores buying intent     │
 │    • Assigns lead to Sales Rep (Round-Robin)           │
 │    • Schedules Follow-Up Task (Quiet Hours checked)    │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 5. SALES REP EXPERIENCE (Next.js Dashboard)            │
 │    • Notification Bell badge lights up (60s poll)      │
 │    • Rep opens Lead Detail page & reads AI Card        │
 │    • Rep replies via 24h WhatsApp compliance window    │
 │    • Recharts analytics dashboard updates live         │
 └────────────────────────────────────────────────────────┘
```

---

## 2. Function-by-Function Map

Here is the exact map of which function talks to which function, what goes in, and what comes out. You can match these names directly to the code files in your project.

### Group A: Logging In & Protecting the "Front Door" (Authentication)

| Function | Found In | Called By | What It Calls | Input (Data In) | Output (Data Out) | Plain-English Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `login` | `backend/app/modules/auth/router.py` | Web browser (`POST /api/v1/auth/login`) | `service.login()` | `LoginRequest` (email & password) | Access token + CSRF token + user profile | Verifies credentials and starts a secure session. |
| `service.login` | `backend/app/modules/auth/service.py` | `auth/router.py:login` | `verify_password()`, `start_session()` | DB session, email, plain password | Session tokens dict or MFA challenge | Verifies the Argon2id password hash against the database. |
| `start_session` | `backend/app/modules/auth/sessions.py` | `auth/service.py` | `create_access_token()`, `_new_token()` | User ID, IP, user-agent | Tokens dict (`access_token`, `refresh_token`) | Generates a new family chain of refresh tokens with reuse detection. |
| `get_tenant_context` | `backend/app/core/tenancy.py` | FastAPI `Depends()` on almost every route | `_claims()`, `_check_user_and_session()`, `_set_context()` | HTTP Header `Authorization`, `X-Tenant-ID` | `TenantContext` object | The digital security guard: confirms the user is active, not suspended, and belongs to this tenant. |
| `_set_context` | `backend/app/core/tenancy.py` | `get_tenant_context` | Database SQL `SELECT set_config('app.tenant_id', ...)` | PostgreSQL session, tenant UUID | None | Tells PostgreSQL: *"Only allow this transaction to see rows belonging to this tenant ID."* |

---

### Group B: Capturing Leads from the Outside World

| Function | Found In | Called By | What It Calls | Input (Data In) | Output (Data Out) | Plain-English Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `post_form_submission` | `backend/app/modules/lead_forms/router.py` | Customer browser (`POST /api/v1/public/forms/{id}/submit`) | `submit_public_form()` | Form public ID, form fields | `{ status: "received" }` | Public doorway for website inquiries; protects server with 16KB body limit. |
| `submit_public_form` | `backend/app/modules/lead_forms/service.py` | `lead_forms/router.py` | `capture_lead()` | Form ID, submission data | Lead reference string | Checks if the hidden honeypot spam field was touched; if clean, passes to capture. |
| `capture_lead` | `backend/app/modules/leads/capture.py` | `submit_public_form()`, Meta/WhatsApp webhooks | `_lookup_existing()`, `deduplicate_and_merge()`, `create_outbox_event()` | Customer name, phone, email, notes, tenant ID | `Lead` database object | Looks for existing records. If none found, creates a new lead and fires a `lead.created` event. |
| `deduplicate_and_merge`| `backend/app/modules/leads/capture.py` | `capture_lead()` | Database updates | Existing lead row, new incoming data | Updated `Lead` row | If Rahim submits twice with the same phone number, merges notes instead of cluttering the CRM with duplicates. |

---

### Group C: The Guaranteed Delivery System (Outbox & Automation)

| Function | Found In | Called By | What It Calls | Input (Data In) | Output (Data Out) | Plain-English Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `create_outbox_event` | `backend/app/core/outbox.py` | `capture_lead()`, `tasks/service.py` | Database `INSERT INTO outbox_events` | Event type (`lead.created`), tenant ID, payload dict | `OutboxEvent` row | Saves the event into the database inside the *exact same transaction* as the lead, guaranteeing it cannot be lost. |
| `poll_and_dispatch` | `backend/app/core/dispatcher.py` | Continuous background worker | `claim_batch()`, `sign_and_dispatch()` | Batch size (10), lease seconds (300) | Count of processed events | Uses Postgres `FOR UPDATE SKIP LOCKED` to safely pick up pending events across multiple server processes. |
| `sign_and_dispatch` | `backend/app/core/dispatcher.py` | `dispatcher.py` | `sign_payload()`, `httpx.post()` | Outbox event row | HTTP Response from n8n | Signs the message with HMAC-SHA256 wax seal so n8n knows it came genuinely from Syntrix CRM. |

---

### Group D: The AI Concierge (Qualification & Recommendations)

| Function | Found In | Called By | What It Calls | Input (Data In) | Output (Data Out) | Plain-English Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `assess_lead_job` | `backend/app/modules/ai/jobs.py` | Automation endpoint (`POST /internal/v1/automation/leads/{id}/assess`) | `AnthropicAdapter.analyze_lead()`, `create_assessment()` | Lead ID, tenant ID | AI Assessment record | Fetches customer inquiry notes, feeds them to the LLM, and stores the structured verdict. |
| `analyze_lead` | `backend/app/modules/ai/adapter.py` | `jobs.py:assess_lead_job` | Anthropic / OpenAI API | Cleaned customer text prompt | `LeadAssessmentResult` (JSON) | Calls the external AI model and parses the output into sentiment, intent, and recommended action. |

---

### Group E: Task Follow-ups, Quiet Hours & WhatsApp Messaging

| Function | Found In | Called By | What It Calls | Input (Data In) | Output (Data Out) | Plain-English Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `create_task` | `backend/app/modules/tasks/service.py` | n8n Workflow A, Sales Reps | `record_audit_event()`, `create_outbox_event()` | Lead ID, assigned rep, due date, type | `Task` row | Schedules a follow-up action for the sales representative. |
| `is_quiet_hours` | `backend/app/modules/automation/service.py` | Task executor, n8n Workflow B | Database `tenant_settings` | Tenant ID, current time | `True` or `False` | Checks if current local time is inside the company's quiet window (e.g. 21:00 to 09:00 in Asia/Dhaka). |
| `send_message` | `backend/app/modules/messaging/service.py` | Sales rep in inbox (`POST /api/v1/messages`) | `is_window_active()`, `MetaProvider.send_message()` | Conversation ID, text or template name | `Message` database record | Enforces Meta's 24-hour compliance window. Sends pre-approved template if window has closed. |
| `handle_inbound_message`| `backend/app/modules/integrations/inbound.py` | Meta Webhook router | `pause_active_tasks()`, `create_notification()` | Inbound customer WhatsApp text | Processed status | When customer says *"Yes, I am interested"*, automatically pauses automated reminders and alerts the sales rep. |

---

## 3. Detailed Walkthrough

Let us follow a concrete, real-life story from beginning to end to see how every piece of software connects.

### The Characters
- **Acme Traders**: A real estate & office interior company in Dhaka.
- **Rahim Uddin**: A potential customer looking for an office renovation.
- **Nusrat**: A senior sales representative working at Acme Traders.

---

### Step 1: Rahim Fills Out the Website Form
Rahim visits Acme's website. Embedded on the page is an HTML form powered by your backend ([lead_forms/router.py](file:///e:/Sales%20assist/Sus/backend/app/modules/lead_forms/router.py)):
- **Full Name**: Rahim Uddin
- **Email**: `rahim@example.com`
- **Phone**: `+8801712345678`
- **Message**: *"We need a complete interior renovation for our 2,500 sq ft office in Banani. Budget is around 500,000 BDT. Please contact me soon."*

When Rahim clicks **"Submit"**, the browser sends an HTTP `POST` request to:
```http
POST /api/v1/public/forms/lf_9a8b7c6d5e4f/submit
Content-Type: application/json

{
  "name": "Rahim Uddin",
  "email": "rahim@example.com",
  "phone": "+8801712345678",
  "notes": "We need a complete interior renovation...",
  "company_website": ""
}
```

---

### Step 2: Honeypot & Body Guard
In [lead_forms/router.py](file:///e:/Sales%20assist/Sus/backend/app/modules/lead_forms/router.py), the `LimitedBodyRoute` class verifies that the request size is less than 16 Kilobytes. This prevents malicious attackers from flooding the server memory with huge files.

Next, [submit_public_form](file:///e:/Sales%20assist/Sus/backend/app/modules/lead_forms/service.py) inspects the `company_website` field. 
- Humans cannot see this field because it is hidden with CSS (`display: none`).
- Spambots fill in every field they see. If `company_website` contains any text, the function returns an immediate fake success (`{ "status": "received" }`) and drops the request without touching the CRM database.
- Rahim is a real human, so `company_website` is blank. The submission proceeds.

---

### Step 3: Tenant Identification & Lead Deduplication
The code looks up which company owns form `lf_9a8b7c6d5e4f`. It discovers the form belongs to **Acme Traders** (`tenant_id = 11111111-2222-3333-4444-555555555555`).

It passes Rahim's information to `capture_lead()` in [leads/capture.py](file:///e:/Sales%20assist/Sus/backend/app/modules/leads/capture.py).
1. `_lookup_existing()` runs an SQL query checking: *Does Acme already have a lead with phone `+8801712345678` or email `rahim@example.com`?*
2. Since Rahim is brand new, it creates a new row in the `leads` table with `status = "new"`.
3. It sanitizes his text (removes invisible Unicode control codes).

---

### Step 4: The Database Lock & Row-Level Security
When saving Rahim's lead, SQLAlchemy communicates with PostgreSQL. Before any row is written, your application runs:
```sql
SELECT set_config('app.tenant_id', '11111111-2222-3333-4444-555555555555', true);
```
PostgreSQL's engine checks its security rules:
```sql
CREATE POLICY leads_tenant_isolation ON leads 
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```
Because of this rule, even if an attacker attempts an SQL injection or a bug occurs in the backend, PostgreSQL physically refuses to read or write any rows unless the `tenant_id` matches. **Acme's data and Globex's data remain completely isolated.**

---

### Step 5: Guaranteed Event Dispatch (The Outbox Pattern)
Here is a classic software trap: what if the server saves Rahim's lead to the database, but right before it tells the AI to process it, the internet hiccups or the server restarts? Rahim would be stuck in the database forever with no salesperson ever contacting him.

To make this bulletproof, your system uses the **Transactional Outbox Pattern** ([core/outbox.py](file:///e:/Sales%20assist/Sus/backend/app/core/outbox.py)):
1. Inside the **exact same database transaction** that creates Rahim's lead row, it inserts a row into the `outbox_events` table:
   - `event_type`: `"lead.created"`
   - `aggregate_id`: Rahim's Lead UUID
   - `payload`: Rahim's sanitized inquiry
   - `status`: `"pending"`
2. If the database crashes, neither Rahim nor the event is saved. If the database commits, **both are guaranteed to be saved together**.

---

### Step 6: Dispatcher & n8n Automation
Running continuously in the background is the **Dispatcher Worker** ([core/dispatcher.py](file:///e:/Sales%20assist/Sus/backend/app/core/dispatcher.py)):
1. Every 2 seconds, it queries `outbox_events` for rows where `status = 'pending'`.
2. It uses `FOR UPDATE SKIP LOCKED`. This allows you to run 10 servers simultaneously without them ever duplicating work or fighting over the same event.
3. The dispatcher generates an **HMAC-SHA256 digital signature** using a shared secret key and posts the event to your self-hosted **n8n automation workflow** (`n8n/workflows/workflow_a_new_lead.json`).

---

### Step 7: The AI Concierge Evaluates Rahim
n8n orchestrates the qualification process by calling `assess_lead_job()` in [ai/jobs.py](file:///e:/Sales%20assist/Sus/backend/app/modules/ai/jobs.py):
1. **PII Scrubbing**: Before sending text to the AI model, the system removes sensitive personal details to protect Rahim's privacy.
2. **Anthropic/OpenAI Adapter** ([ai/adapter.py](file:///e:/Sales%20assist/Sus/backend/app/modules/ai/adapter.py)): Sends Rahim's message to the Large Language Model with strict instructions to return a JSON object adhering to this schema:
   ```json
   {
     "intent": "office_renovation_inquiry",
     "sentiment": "positive",
     "confidence": 0.94,
     "urgency": "high",
     "estimated_budget": "500000 BDT",
     "recommended_action": "call_within_1_hour",
     "suggested_reply": "Hello Rahim! Thank you for contacting Acme Traders regarding your Banani office renovation. Our senior commercial designer will call you shortly."
   }
   ```
3. **Pydantic Validation**: [ai/schemas.py](file:///e:/Sales%20assist/Sus/backend/app/modules/ai/schemas.py) validates that the AI output strictly matches this structure. If the AI hallucinated or returned invalid text, Pydantic catches it immediately, preventing crashes.

---

### Step 8: Sales Rep Assignment & Bangladesh Quiet Hours
1. **Round-Robin Assignment**: The system assigns Rahim to sales rep **Nusrat** because she has the fewest active leads on the commercial design team.
2. **Task Creation**: It creates a follow-up task: *"Call Rahim Uddin (Banani Renovation)"* assigned to Nusrat.
3. **Quiet Hours Check** ([modules/automation/service.py](file:///e:/Sales%20assist/Sus/backend/app/modules/automation/service.py)):
   - Suppose Rahim submitted this form at **10:45 PM** Bangladesh time.
   - Acme's settings state that quiet hours run from **21:00 (9:00 PM)** to **09:00 (9:00 AM)**.
   - The system calculates that 10:45 PM is inside quiet hours.
   - It reschedules the initial outbound follow-up task to **tomorrow at 09:15 AM**, emitting an event with reason `"quiet_hours"`.

---

### Step 9: Nusrat Logs In (Next.js Frontend)
The next morning, Nusrat opens `http://localhost:3000` on her laptop:
1. She enters her email `rep1@acme.test` and password `ChangeMe!12345`.
2. The browser calls `POST /api/v1/auth/login` ([modules/auth/router.py](file:///e:/Sales%20assist/Sus/backend/app/modules/auth/router.py)).
3. The server sets a secure, encrypted `HttpOnly` refresh cookie in her browser and gives her a short-lived JSON Web Token (JWT) in frontend memory ([frontend/src/lib/auth/token-store.ts](file:///e:/Sales%20assist/Sus/frontend/src/lib/auth/token-store.ts)).
4. Nusrat's browser **never stores tokens in LocalStorage**. If an attacker injects a malicious script via an ad or browser extension, they cannot steal her session.

---

### Step 10: The Interactive Workspace Experience
1. **Notification Bell** ([frontend/src/components/layout/notification-bell.tsx](file:///e:/Sales%20assist/Sus/frontend/src/components/layout/notification-bell.tsx)):
   - TanStack Query polls `GET /api/v1/notifications?read=false` every 60 seconds.
   - A red badge with `"1"` appears over the bell.
   - Nusrat clicks the bell and sees: *"New qualified lead assigned: Rahim Uddin (500k BDT Budget)"*.
2. **Lead Detail AI Card** ([frontend/src/app/leads/[id]/page.tsx](file:///e:/Sales%20assist/Sus/frontend/src/app/leads/%5Bid%5D/page.tsx)):
   - Nusrat clicks the notification and lands on Rahim's profile.
   - She sees the **AI Assessment Card**:
     - Sentiment: **Positive (Green badge)**
     - Intent: **Office Renovation**
     - Confidence: **94%**
     - Suggested Action: *"Call within 1 hour"*
3. **Conversations Inbox** ([frontend/src/app/conversations/page.tsx](file:///e:/Sales%20assist/Sus/frontend/src/app/conversations/page.tsx)):
   - Nusrat opens the conversation thread.
   - Because Rahim initiated contact on the website form and agreed to WhatsApp messaging, the Meta 24-hour compliance window is active.
   - Nusrat clicks **"Use Suggested AI Reply"**, adjusts one sentence, and clicks **Send**.
4. **Outbound Messaging Pipeline** ([modules/messaging/service.py](file:///e:/Sales%20assist/Sus/backend/app/modules/messaging/service.py)):
   - The message is recorded in Postgres first.
   - The encrypted WhatsApp access token is decrypted using AES-256-GCM.
   - The WhatsApp Cloud API delivers the message directly to Rahim's phone.

---

### Step 11: Rahim Replies on WhatsApp
Rahim pulls out his phone and replies: *"Thanks Nusrat, 11 AM works for a quick phone call."*

1. Meta's servers send a webhook to `POST /api/v1/webhooks/meta` ([modules/integrations/webhooks.py](file:///e:/Sales%20assist/Sus/backend/app/modules/integrations/webhooks.py)).
2. **Signature Verification**: Before reading the JSON body, the server checks the `X-Hub-Signature-256` header against Acme's app secret. Fake requests are rejected instantly with HTTP 401.
3. **Task Pause on Customer Reply** ([modules/tasks/events.py](file:///e:/Sales%20assist/Sus/backend/app/modules/tasks/events.py)):
   - Because the customer replied, any generic automated "Reminder: Are you still looking for interior design?" follow-up tasks are automatically **paused**!
   - This ensures customers never get annoying robotic reminders right after they just replied to a real person.
4. **Live UI Refresh**: Nusrat's conversations inbox automatically updates to show Rahim's latest message.

---

## 4. Glossary of Tools and Concepts

Here is every technical term and library used in your project, explained with everyday analogies.

### 1. SaaS & Multi-Tenancy
* **What it means**: "Software as a Service" where one running copy of the program serves multiple different companies (tenants).
* **Everyday Analogy**: An apartment building. Everyone shares the building structure (the server and database), but every tenant has their own private key and apartment walls (tenant isolation). Company A cannot see Company B's belongings.

### 2. PostgreSQL Row-Level Security (RLS)
* **What it means**: A feature built into the PostgreSQL database engine that checks whether the current user is allowed to see each individual row in a table.
* **Everyday Analogy**: An airport security badge. When your badge says "Terminal 1", the electronic doors in Terminal 2 will physically not unlock for you, even if you try to turn the handle.

### 3. FastAPI & Pydantic v2
* **What it means**: FastAPI is the Python web framework that receives HTTP requests from browsers and mobile phones. Pydantic is its security guard that validates data.
* **Everyday Analogy**: The customs inspector at the border. If a form is missing a required passport number or the phone number format is malformed, Pydantic stops it at the gate and returns a clear error message before it can enter the rest of the application.

### 4. SQLAlchemy 2 & Alembic
* **What it means**: SQLAlchemy is an Object-Relational Mapper (ORM) that lets Python code talk to PostgreSQL using Python objects instead of raw SQL strings. Alembic is the tool that tracks database schema changes over time.
* **Everyday Analogy**: 
  - SQLAlchemy is a multilingual translator who translates Python commands into fluent SQL.
  - Alembic is a blueprint change-log for an architect. Each blueprint modification (like adding a `read_at` column) has a timestamped revision number so every developer's database stays in identical sync.

### 5. Transactional Outbox Pattern
* **What it means**: A design pattern where events destined for other systems (like n8n or an email service) are saved in the database inside the same transaction as the business data, and sent by a background worker.
* **Everyday Analogy**: Leaving outgoing letters in your building's outgoing mail chute. You don't have to wait for the postman to arrive before continuing your day; the mail chute guarantees your letter will be collected and delivered.

### 6. HMAC-SHA256 Signatures
* **What it means**: "Hash-based Message Authentication Code". A mathematical way to prove that a message came from a trusted sender and was not altered in transit.
* **Everyday Analogy**: A royal wax seal stamped with a king's signet ring. If the seal is broken or does not match the ring, the recipient knows the letter was tampered with and discards it.

### 7. n8n Automation Engine
* **What it means**: A visual workflow automation platform hosted inside your Docker environment that connects triggers (like a new lead) to multi-step actions (calling AI, delaying for quiet hours, notifying reps).
* **Everyday Analogy**: A smart factory conveyor belt. When an item arrives, robotic arms inspect it, apply labels, sort it into the right bin, and sound a chime for the floor manager.

### 8. Argon2id Password Hashing
* **What it means**: The state-of-the-art password hashing algorithm (winner of the Password Hashing Competition). It turns passwords into irreversible scrambled strings.
* **Everyday Analogy**: Dropping an intricate glass sculpture into an industrial blender. You can never reconstruct the original sculpture from the crushed powder, but if someone brings an identical sculpture and blends it, the resulting powder will match identically.

### 9. JWT & Refresh Token Rotation
* **What it means**: A short-lived JSON Web Token (lasts 15 minutes) kept in browser memory, paired with a long-lived Refresh Token stored in a secure `HttpOnly` browser cookie.
* **Everyday Analogy**: A hotel keycard. The keycard only unlocks your room for today. If it expires, you show your physical passport at the front desk to get a renewed card. If someone steals an old keycard, the hotel detects reuse and instantly cancels the entire family of cards.

### 10. TOTP MFA (Multi-Factor Authentication)
* **What it means**: "Time-based One-Time Password". 6-digit codes generated on an authenticator app (like Google Authenticator) that change every 30 seconds.
* **Everyday Analogy**: A bank safe deposit box that requires two keys: your physical key and the bank manager's guard key turned simultaneously.

### 11. Next.js App Router & React
* **What it means**: A modern JavaScript framework for building fast, responsive user interfaces. React builds reusable components (like buttons and cards), while Next.js handles routing and fast page loading.
* **Everyday Analogy**: A modular physical store. Instead of tearing down the entire building whenever a customer asks for a new shoe size, the store updates just the display shelf in front of them instantly.

### 12. TanStack Query
* **What it means**: A library for React that handles fetching data from the backend, caching it in memory, and refetching it in the background.
* **Everyday Analogy**: A smart personal assistant who keeps a copy of today's schedule on their notepad. When you ask for the schedule, they read it instantly from memory, while quietly checking the master calendar in the background to see if any meeting times changed.

### 13. Recharts
* **What it means**: A data visualization library for React that turns raw numbers and arrays into interactive bar charts, funnel diagrams, and trend lines.
* **Everyday Analogy**: The instrument cluster in a car. It takes raw electrical signals from the engine and presents them as a clear, intuitive speedometer and fuel gauge.

### 14. Anti-Spam Honeypot
* **What it means**: A hidden form field that is invisible to human users but visible to automated scrapers and bots.
* **Everyday Analogy**: An invisible laser tripwire. Normal guests walk right through the open hallway, but an intruder crawling through hidden vents trips the alarm and is quietly escorted out.

### 15. Meta 24-Hour WhatsApp Messaging Window
* **What it means**: A strict privacy policy enforced by Meta (Facebook/WhatsApp). When a customer sends a message, a company has exactly 24 hours to reply with freeform text. After 24 hours, the company can only send pre-approved template messages.
* **Everyday Analogy**: A retail store helpline. While you are talking to the representative, they can converse freely. But once you hang up and a day passes, they can only send you pre-formatted official service updates so they don't spam your personal phone.

---

## Summary: How Everything Fits Together
Your application is built with a clear separation of responsibilities:
- **Next.js** provides a clean, responsive interface for sales teams.
- **FastAPI** acts as the secure, high-speed gatekeeper and business logic engine.
- **PostgreSQL with RLS** guarantees that data stays safe, private, and permanently separated between companies.
- **n8n & the LLM Adapter** remove repetitive qualification busywork, turning raw incoming inquiries into prioritized, actionable sales opportunities within seconds.
