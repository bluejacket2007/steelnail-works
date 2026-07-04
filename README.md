# SteelNail Works — Enterprise B2B Marketplace

**Deploying this for real?** See [DEPLOYMENT.md](DEPLOYMENT.md) — a
step-by-step runbook for Vercel (frontend) + Render (backend, private
Postgres, private Redis), plus a go-live security checklist.

IndiaMART-style B2B marketplace for a steel nail manufacturing factory:
heavily-normalized industrial catalog, bulk volume negotiation via an
autonomous AI agent, multi-tier (30/70) milestone payments, and a hardened
security posture across the stack — with a full public marketing site and
an authenticated buyer/staff dashboard.

## Architecture

```
nail-factory-website/
├── .github/workflows/ci.yml      # pytest + frontend typecheck/build on push/PR
├── docker-compose.yml            # postgres + redis + backend + frontend, healthchecked
├── backend/                      # Python / FastAPI microservice
│   ├── requirements.txt
│   ├── requirements-dev.txt      # + pytest, fakeredis
│   ├── pytest.ini
│   ├── tests/                    # 53 tests — no live Postgres/Redis required
│   ├── .env.example              # every secret & tuning knob
│   ├── alembic.ini / migrations/ # production schema migrations
│   ├── scripts/seed.py           # demo catalog, tiers, stock, manager login
│   └── app/
│       ├── main.py               # app factory + middleware stack
│       ├── core/
│       │   ├── config.py         # env-driven settings (pool sizing, secrets)
│       │   ├── database.py       # SQLAlchemy engine, pooled connections
│       │   ├── redis_client.py   # sync + async Redis pools
│       │   ├── security.py       # JWT (15-min access / rotating refresh),
│       │   │                     #   bcrypt, Fernet EncryptedString column
│       │   └── rbac.py           # require_roles() RBAC guards
│       ├── middleware/
│       │   ├── rate_limiter.py   # Redis token bucket (60/min IP, 200/min user)
│       │   ├── security_headers.py  # HSTS/CSP/nosniff/etc.
│       │   ├── sanitizer.py      # automated XSS escaping of JSON bodies
│       │   └── idempotency.py    # X-Idempotency-Key replay/lock framework
│       ├── models/models.py      # full relational schema (see below)
│       ├── schemas/schemas.py    # pydantic API contracts
│       ├── payments/
│       │   ├── base.py           # unified provider interface
│       │   ├── stripe_provider.py    # PaymentIntents + HMAC sig verification
│       │   ├── razorpay_provider.py  # Orders API + HMAC sig verification
│       │   ├── milestones.py     # 30/70 split state machine + hash-chain ledger
│       │   ├── webhooks.py       # verified, deduped, async webhook workers
│       │   └── invoices.py       # proforma invoice PDF generation
│       ├── agent/
│       │   ├── engine.py         # Claude tool-calling loop, Redis memory
│       │   ├── tools.py          # 4 callable tools + Anthropic schemas
│       │   └── guardrails.py     # hard 12% net-margin floor enforcement
│       └── api/                  # auth, catalog, rfq, quotes, payments,
│                                  #   admin, contact, agent_chat, webhooks
└── frontend/                     # Next.js 15 (App Router) web application
    ├── .env.example               # publishable/public payment keys, API base URL
    ├── app/
    │   ├── (marketing)/          # public site: home, catalog, product detail,
    │   │                         #   about, how-it-works, contact
    │   ├── login/ register/      # auth pages (Suspense-wrapped, honor ?next=)
    │   └── dashboard/            # protected app: RFQs, orders, orgs, inquiries
    ├── components/                # SiteNavbar, SiteFooter, AgentChat,
    │                              #   StripePaymentForm, RazorpayButton
    └── lib/                        # typed API client, auth context, design tokens
```

### Database schema (PostgreSQL, SQLAlchemy 2.0)

| Module | Tables | Notes |
|---|---|---|
| Users & Organizations | `organizations`, `users` | GSTIN/EIN, credit ratings, parent-company self-relation; bank details & PII encrypted at rest |
| Products & Attributes | `products`, `product_attributes`, `warehouse_stock` | length (mm/in), wire gauge (AWG/mm), head/shank/finish enums; **composite indexes** `(length_mm, wire_gauge_mm, finish)` and `(finish, shank_type, head_style)` for faceted search |
| Tiered Bulk Pricing | `bulk_pricing_tiers` | SKU × MOQ range (1–5 t, 5–20 t, 20+ t) × price/kg |
| RFQ State Machine | `rfqs`, `quotes` | `RFQ_Submitted → AI_Negotiating → Sales_Review → Approved → Contract_Generated → Fulfilled`; illegal transitions rejected; negotiation transcripts encrypted |
| Orders & Finance | `orders`, `order_milestones`, `ledger_entries`, `webhook_events` | 30/70 milestones, BoL verification gate, SHA-256 hash-chained append-only ledger, webhook dedupe |
| Contact Inquiries | `contact_inquiries` | Public marketing-site lead capture, staff-reviewable |

Production schema changes go through **Alembic** (`backend/alembic.ini` +
`backend/migrations/`, sourcing `DATABASE_URL` from the same `Settings`
object the app uses) instead of the dev-only `AUTO_CREATE_TABLES` flag.

### Security model

- **AuthN/AuthZ** — OAuth2 password flow; 15-minute stateless JWT access
  tokens; refresh tokens in `HttpOnly; SameSite=Strict; Secure` cookies,
  rotated on use and revocable via a Redis allowlist. RBAC roles:
  `SuperAdmin`, `SalesManager`, `SalesRep`, `ClientProcurement` enforced by
  `require_roles()` on every protected route.
- **SQLi** — all data access via SQLAlchemy's parameterized query compiler;
  no string-built SQL exists in the codebase.
- **Encryption at rest** — Fernet (`cryptography`) `EncryptedString` columns
  for banking details, PII, and negotiation histories; `MultiFernet` gives
  zero-downtime key rotation via `FERNET_KEYS`.
- **Rate limiting** — atomic Redis Lua token bucket: 60 req/min per
  unauthenticated IP, 200 req/min per authenticated user, shared across
  replicas; 429 + `Retry-After` on exhaustion. The public contact form runs
  through the same anonymous-tier limiter.
- **XSS** — inbound JSON strings HTML-escaped by middleware before reaching
  handlers (webhook and auth routes exempted); strict CSP on responses.
- **CORS / hosts** — explicit origin allowlist, TrustedHost, optional HTTPS
  redirect.
- **TLS 1.3** — terminate at the edge proxy; HSTS (2y, preload) is set by the
  API. Example nginx listener:

  ```nginx
  server {
      listen 443 ssl http2;
      ssl_protocols TLSv1.3;            # TLS 1.3 only, globally
      ssl_certificate     /etc/ssl/fullchain.pem;
      ssl_certificate_key /etc/ssl/privkey.pem;
      location / { proxy_pass http://backend:8000; proxy_set_header X-Forwarded-For $remote_addr; }
  }
  ```

### RFQ → Quote → Order lifecycle

1. Buyer submits an **RFQ** for a SKU + volume.
2. Sales staff (or the AI agent) negotiate; staff move the RFQ through
   `AI_Negotiating → Sales_Review → Approved` via `/rfqs/{id}/transition`
   (Approve/Reject/Contract-generate are `SalesManager`-only).
3. Staff issue a **Quote** on the RFQ (also margin-floor-checked).
4. Once the RFQ is `Approved`, the buyer **accepts** the quote —
   atomically creating the `Order`, splitting it into 30/70
   `OrderMilestone`s, and advancing the RFQ to `Contract_Generated`.
5. Buyer pays the 30% advance → order → `In_Production`.
6. Buyer uploads a Bill of Lading; a `SalesManager` verifies it → order →
   `Awaiting_Balance`.
7. Buyer pays the 70% balance → order → `Shipped`, and the originating RFQ
   auto-transitions to `Fulfilled`.

### Payments (Stripe + Razorpay behind one interface)

- **Milestone split state machine** — 30% advance releases production; the
  70% balance can only be initiated after the advance is `PAID` **and** a
  Bill of Lading has been uploaded and verified by a `SalesManager`.
- **Idempotency** — `X-Idempotency-Key` is mandatory on payment POSTs;
  concurrent duplicates get 409, completed duplicates get a byte-identical
  cached replay, and the key is also forwarded to the provider so double
  capture is impossible end-to-end.
- **Webhook ledger** — HMAC-SHA256 signature verification (constant-time
  compare, 5-min replay tolerance for Stripe), unique-event dedupe, async
  background processing that settles the milestone, appends a hash-chained
  ledger entry, and generates a proforma invoice PDF.

### AI negotiation agent (Anthropic Claude)

- Model `claude-opus-4-8` with adaptive thinking; manual tool-use loop so
  every tool call passes through guardrails.
- Conversation memory cached in Redis per session (`agent:session:{id}`,
  rolling 24h TTL), namespaced by buyer organization.
- Tools: `check_warehouse_stock`, `calculate_tiered_price`,
  `evaluate_custom_discount`, `escalate_to_human_sales` (CRM flash via Redis
  list + pub/sub).
- **Hard margin guardrail** — floor = (wire-rod cost + processing overhead)
  × finish premium ÷ (1 − 12%). Enforced three times: inside price-producing
  tools (`@margin_guarded`), on discount approval, and by a final regex audit
  of the outbound reply. A sub-floor offer is suppressed and auto-escalated —
  the model cannot bypass it by prompt manipulation.

### Frontend

- **Public marketing site** (`app/(marketing)/`) — hero homepage with
  featured products, a full catalog browser with server-rendered facet
  filters (finish, shank type, head style, length range), per-product detail
  pages with the full spec sheet and pricing tier table, About, How-it-Works,
  and a Contact page backed by the real `contact_inquiries` endpoint.
- **Auth** (`lib/auth-context.tsx`) — access token held in memory only;
  silently re-minted on page load via the `HttpOnly` refresh cookie. Login
  and register honor a `?next=` redirect target end-to-end.
- **Dashboard** (`app/dashboard/`) — role-aware nav; RFQ submission and
  lifecycle management, quote issuance/acceptance, order milestone tracking
  with real Stripe Elements / Razorpay Checkout.js payment flows and
  Bill-of-Lading upload/verify, an org credit-rating editor, and a staff
  inbox for contact inquiries.
- `components/StripePaymentForm.tsx` / `RazorpayButton.tsx` — once
  `/payments/initiate` returns an intent, these mount the provider's real
  hosted UI (`@stripe/react-stripe-js` PaymentElement, or a dynamically
  loaded `checkout.razorpay.com/v1/checkout.js` modal) rather than a stub.
  Requires `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` / `NEXT_PUBLIC_RAZORPAY_KEY_ID`
  (see `frontend/.env.example`); both components render a clear
  "not configured" notice instead of crashing if the key is absent.
- `components/AgentChat.tsx` — embedded negotiation chat on the RFQ detail
  page; shows which tools the agent called and surfaces escalation tickets.

## Running locally

```bash
# 1. Infrastructure + services
cp backend/.env.example backend/.env      # fill in secrets
docker compose up --build

# — or run the backend directly —
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
python -m scripts.seed                            # demo catalog + manager login
uvicorn app.main:app --reload                     # http://localhost:8000/docs

# 2. Frontend
cd frontend
npm install && npm run dev                        # http://localhost:3000
```

Required secrets in `backend/.env`: `JWT_SECRET`, `FERNET_KEYS`,
`ANTHROPIC_API_KEY`, Stripe/Razorpay keys + webhook secrets. Generation
commands are inline in `.env.example`.

## API surface

| Area | Endpoints |
|---|---|
| Auth | `POST /api/v1/auth/register` · `login` · `refresh` · `logout` · `GET me` |
| Catalog | `GET /api/v1/catalog/products` (faceted filters) · `GET /products/{sku}` |
| RFQ | `POST /api/v1/rfqs` · `GET /rfqs` · `GET /rfqs/{id}` · `POST /rfqs/{id}/transition` |
| Quotes | `POST /rfqs/{id}/quotes` · `GET /rfqs/{id}/quotes` · `POST /quotes/{id}/accept` |
| Payments | `GET /payments/orders` · `GET /orders/{id}` · `POST /payments/initiate` · `POST /milestones/{id}/bol` · `POST /milestones/{id}/bol/verify` |
| Admin | `GET /api/v1/orgs` · `GET /orgs/{id}` · `PATCH /orgs/{id}/credit` |
| Contact | `POST /api/v1/contact` (public) · `GET /contact` (staff) · `POST /contact/{id}/handled` |
| Agent | `POST /api/v1/agent/chat` · `DELETE /agent/chat/{session_id}` |
| Webhooks | `POST /api/v1/webhooks/stripe` · `POST /api/v1/webhooks/razorpay` |

Interactive OpenAPI docs at `http://localhost:8000/docs`.

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest -v      # 53 tests, no live Postgres/Redis required
```

The suite runs the real application code against an in-memory SQLite DB
(`app/core/database.py` is dialect-aware: QueuePool + Postgres in production,
`StaticPool` + SQLite in tests) and a `fakeredis` instance where Redis is
touched (refresh-token allowlist, the escalation queue). It covers the RFQ
state machine, the margin-floor guardrail and all four agent tools, the
30/70 milestone state machine and hash-chained ledger, JWT/password/Fernet
primitives, and Stripe/Razorpay webhook signature verification (valid,
tampered, and expired-timestamp cases).

## Verification performed

- `python -m compileall app scripts migrations tests` — every backend module compiles.
- `pytest` — 53/53 passing (see **Testing** above).
- `npx tsc --noEmit` / `npx next build` — zero type errors; full production
  build succeeds across all 17 frontend routes.
- **A real local end-to-end run.** This machine has no Docker, PostgreSQL, or
  Redis installed, so rather than skip verification, the actual FastAPI app
  (`app.main:app`) was run through Starlette's `TestClient` — a genuine ASGI
  transport exercising the real middleware stack and routers — substituting
  SQLite for Postgres and `fakeredis` for Redis (patched only in the
  throwaway test harness, never in application code). It walked the full
  lifecycle: register → login → catalog search → RFQ → quote (including a
  below-floor quote correctly rejected with 422) → RBAC-gated transitions →
  quote acceptance → 30/70 milestones → BoL upload/verify → org credit
  update → public contact form → staff inbox. A second pass booted a real
  `uvicorn` server plus the actual Next.js dev server and drove the buyer
  flow (register → dashboard → submit RFQ) through an actual browser,
  including confirming the session survives a full page reload via the
  silent refresh-cookie flow.
- **This run found and fixed three real bugs**, since fixed and covered by
  regression tests:
  1. `set_refresh_cookie` hardcoded `secure=True`, which any RFC-6265 client
     silently drops on plain HTTP — refresh tokens would never persist on a
     local `uvicorn --reload` / `docker compose up` session without a TLS
     proxy in front. Now tracks `ENFORCE_HTTPS`.
  2. Stripe/Razorpay SDK exceptions (e.g. an invalid/missing API key)
     weren't caught, so a provider auth failure crashed as a raw 500 instead
     of the intended `PaymentError` → clean 502.
  3. The idempotency middleware matched *any* POST under `/api/v1/payments`,
     so Bill-of-Lading upload/verification — which never call a payment
     provider — incorrectly demanded an `X-Idempotency-Key`. Scoped to the
     one route that actually needs it: `POST /payments/initiate`.

Card entry / OTP itself can't be demonstrated without live Stripe/Razorpay
test keys, which this environment doesn't have — both checkout components
were confirmed to reach the real provider SDK and surface a clean error
rather than crash, and everything downstream of a successful provider
response (webhook verification, milestone settlement, ledger append) is
covered directly by the pytest suite.

## CI

`.github/workflows/ci.yml` runs on every push/PR to `main`: the backend job
installs `requirements-dev.txt` and runs `pytest` (SQLite + fakeredis, no
service containers needed); the frontend job runs `tsc --noEmit` and
`next build`. Both mirror exactly what was run manually to verify this
codebase (see **Verification performed**).

## Production notes

- Run `alembic revision --autogenerate` / `alembic upgrade head` instead of
  `AUTO_CREATE_TABLES` once a real Postgres instance is available.
- Run webhook workers on a dedicated queue (Celery/RQ/Arq) instead of
  in-process `BackgroundTasks` at scale.
- Set `ENFORCE_HTTPS=true` behind the TLS 1.3 proxy and pin
  `ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS` to the real domains — this is also
  what flips the refresh cookie's `Secure` attribute back on (see above).
- Store `FERNET_KEYS`, `JWT_SECRET`, and provider secrets in a secrets
  manager; rotate Fernet keys by prepending the new key.
- `docker-compose.yml` now healthchecks every service (backend polls its own
  `/health`, frontend polls `/`) and restarts `unless-stopped`; `frontend`
  won't start proxying until `backend` reports healthy.
- Set the real `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` /
  `NEXT_PUBLIC_RAZORPAY_KEY_ID` (frontend) and `STRIPE_SECRET_KEY` /
  `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` (backend) to move off the
  "not configured" fallback in the checkout components.
