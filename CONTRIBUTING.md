# Contributing

This project is a secure, multi-tenant AI Sales Assistant CRM. Before making changes, read the product and engineering guidance in [guide.txt](./guide.txt), [README.md](./README.md), [SECURITY.md](./SECURITY.md), [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md), and [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md).

> Security comes first. We do not skip or weaken a security control to save time. If a requirement conflicts with schedule, we cut scope instead of cutting security.

## 1. Project mission and guardrails

This project is building a multi-company SaaS CRM with the following non-negotiables:

- A shared PostgreSQL database with tenant isolation via Row-Level Security (RLS)
- Secure authentication and authorization built into the backend
- Webhook validation, deduplication, and safe automation flows
- AI as an advisory layer only; backend code still decides what happens
- Clear role boundaries between sales rep, manager, company admin, and platform admin
- One secure capture pipeline for all lead sources

The product rules are strict:

- Never trust a `tenant_id` from the browser
- Never bypass RLS to save time
- Never accept unauthenticated or unsigned webhook traffic
- Never treat UI-only hiding of controls as an authorization mechanism
- Never merge a feature that breaks multi-tenant isolation

## 2. Team workflow and delivery model

### Working model

The team works in parallel on the same architectural layer, with each developer owning a different feature within that layer. At the end of each day, work is integrated and demoed together.

- All 5 developers work on the same layer at the same time when possible
- Shared contracts must be published early
- Tasks rotate across developers so everyone learns the full project
- Whoever owns a module is responsible for its bugs and documentation

### Daily rhythm

The project expects a structured daily cadence:

- 10:00–10:15: stand-up; yesterday, today, blockers
- 10:15–13:30: build the assigned feature on the day’s layer
- 13:30–14:30: integration window; merge PRs, resolve conflicts, run the full test suite
- 14:30–15:00: team demo and plan for tomorrow

### Branching model

Use the project branch flow exactly:

- `main` = release branch
- `develop` = daily integration branch
- `feature/<dev>-<feature>` = feature branches

Rules:

- Keep PRs small and focused
- Merge to `develop` regularly; do not leave large-bang merges for the final day
- Do not merge a breaking change into `develop` without integration verification

## 3. Code and design expectations

### Before coding

Before starting a task, do all of the following:

- Review the relevant project docs and the current implementation state
- Agree on the API contract or schema before coding
- Post shared contracts early when a change affects multiple developers
- Check whether the change touches auth, RLS, RBAC, webhooks, or migrations
- If the work affects the database, announce the migration before creating it

### API contract first

The project requires contract-first work for shared changes:

- API conventions
- shared schemas
- lead capture service behavior
- dashboard query contracts
- auth flows
- major database changes

If a shared contract changes, publish it early so dependent work is not built against stale assumptions.

### Migrations

Migrations are part of the product design and must be handled carefully:

- Announce migration work before creating it
- Avoid Alembic multiple-head problems
- Review RLS, auth, tenancy, and webhook changes carefully
- Keep migration scope tight and testable

## 4. Review and approval policy

### Ring review

The project uses a ring-review system:

- Dev 1 reviews Dev 2
- Dev 2 reviews Dev 3
- Dev 3 reviews Dev 4
- Dev 4 reviews Dev 5
- Dev 5 reviews Dev 1

This review chain applies to normal PRs.

### Hard tasks (`★`)

Any PR marked with `★` must get two reviewers.

### Security approver

Any PR that touches auth, tenant context/RLS, permissions (RBAC), or webhooks needs two approvals:

1. The normal ring reviewer
2. The security approver

The security approver is:

- Dev 1, unless Dev 1 is the author
- Dev 4 if Dev 1 is the author

This rule has no exceptions.

### Extra review rules

- Mob the first hour on Days 3 and 7 for RLS and webhooks work
- Try to get a senior reviewer for about an hour on Days 3, 7, and 14
- Every PR must pass green CI (lint + tests)
- No PR should skip the required security review path

## 5. Commit and PR standards

### Commit messages

Use conventional commits:

- `feat:` for new features
- `fix:` for bug fixes
- `test:` for tests
- `docs:` for documentation changes

Examples:

- `feat: add lead assignment API`
- `fix: enforce tenant filter in dashboard query`
- `test: add cross-tenant RLS regression case`
- `docs: update contributor workflow`

### PR requirements

Every PR must:

- target `develop`
- pass lint and test checks
- include relevant tests and regression coverage
- be reviewed by the ring reviewer
- include required security approvals for sensitive areas
- be small and easy to reason about
- be documented where the change alters public behavior or contracts

## 6. Security requirements

The security requirements are part of the project contract, not optional extras.

### Required controls

- PostgreSQL RLS on every tenant-owned table
- Auth flows with Argon2id, short-lived JWTs, refresh rotation, and revocation
- Permission checks enforced in backend code, not only in the UI
- Webhook signature verification and deduplication
- MFA for privileged flows where required
- Encrypted integration credentials and secret handling
- Cross-tenant regression tests

### Multi-tenant rules

- Never trust a `tenant_id` from the browser
- Verify membership and role on every request in the backend
- Use composite foreign keys including `tenant_id`
- Require RLS policies on all tenant-owned tables
- Ensure the application DB role is not a superuser and does not bypass RLS
- Keep security-sensitive logic inside the backend layer

### Webhooks and integrations

- Validate all provider signatures
- Reject bad or missing signatures
- Deduplicate incoming events before processing
- Record processing state in the webhook pipeline
- Protect integration credentials and never log secrets or tokens

## 7. Testing and quality gates

All changes must be validated before merge.

### Required expectations

- Linting and tests pass in CI
- Unit, API, and/or E2E tests cover the changed behavior
- Cross-tenant tests are included when tenant isolation is involved
- Auth, RBAC, RLS, and webhook changes include targeted tests
- Changed endpoints are visible in the OpenAPI docs and remain consistent with the API contract

### Definition of done

A task is not complete until all of the following are true:

- [ ] Code is merged into `develop`
- [ ] Unit / API tests were written and pass
- [ ] Tenant isolation is respected; no query runs without tenant context
- [ ] The ring reviewer signed off
- [ ] If the work is `★` or it touches auth, RLS, permissions, or webhooks, the required security approver has signed off
- [ ] The endpoint is visible in `/docs` or equivalent OpenAPI output
- [ ] The feature has been demoed in the end-of-day integration session

## 8. Contribution checklist

Before opening a PR, confirm the following:

- The scope is narrow and easy to review
- The change matches the product and technical direction in the project docs
- Security implications were reviewed before implementation
- Tenant isolation was checked for affected queries and flows
- Tests cover the behavior being changed
- The branch and review rules have been followed
- Any shared contracts or schema changes have been communicated early
- Documentation was updated when behavior or setup changed

## 9. Documentation and ownership

Each module is expected to be maintained by the developer who owns it. That includes:

- keeping the implementation aligned with the current design
- updating relevant docs and shared contracts
- fixing bugs introduced in that area
- ensuring the module stays secure and testable

The project expects ownership, not passive handoff.

## 10. When security conflicts with speed

If a task is blocked by a security requirement, do not weaken the control. Cut scope instead.

This project is intentionally designed around secure defaults and strict review paths. We prefer a smaller, safer MVP over a rushed version that violates tenant isolation or security rules.

## 11. Recommended workflow for contributors

1. Read the project guide and any docs relevant to your module.
2. Confirm the requirements and API contract before starting work.
3. Build in a small, reviewable slice.
4. Run the relevant tests and validate tenant behavior.
5. Open a PR to `develop` with the required reviewers and approvals.
6. Respond to review comments and keep the branch clean.
7. Demonstrate the work in the end-of-day integration window.

## 12. Final reminder

For implementation details and project rules, read [guide.txt](./guide.txt) before starting work.

The project is designed to deliver a secure MVP quickly, but not at the expense of tenant safety, auth integrity, or webhook security. If a decision feels risky, default to the safer option and cut features instead of relaxing the controls.
