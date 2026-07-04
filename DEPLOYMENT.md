# Deployment runbook

**Target:** Vercel (frontend) + Render (backend, private Postgres, private Redis).
See the README for why this split was chosen over a self-hosted VPS — in
short, this stack handles real payments and corporate PII, and both
platforms remove entire classes of self-inflicted server-security mistakes
(unpatched sshd, exposed DB ports, forgotten cert renewal) in exchange for
their compliance posture (Render is SOC 2 Type II) and a small monthly bill.

Do the steps in order — the backend needs to exist before the frontend can
point at it, and CORS needs to point back at the frontend once it exists.

## 0. Prerequisites

- This repo pushed to GitHub (or GitLab/Bitbucket). Both Render and Vercel
  deploy by connecting to a git provider — they can't deploy a local folder.
- A Render account and a Vercel account, each with 2FA enabled.
- Real API keys ready: Stripe (secret + webhook signing secret), Razorpay
  (key id + key secret + webhook secret), Anthropic.
- The real current wire-rod cost and processing overhead per kg from
  whoever runs the factory — these aren't placeholder numbers, they're what
  the AI agent's margin floor is computed from (see `app/agent/guardrails.py`).

## 1. Push to GitHub

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

(This repo is already `git init`'d with an initial commit staged locally —
see the project README for the one prerequisite step left: setting your git
author identity before that commit can be made.)

## 2. Deploy the backend on Render

1. Render dashboard → **New** → **Blueprint** → connect this repo. Render
   detects `render.yaml` and shows three resources: `nailfactory-postgres`,
   `nailfactory-redis`, `nailfactory-backend`.
2. Pick a **paid plan** for all three (not free tier — free web services
   spin down on idle, which breaks a live site people are paying to use;
   free Postgres expires after 90 days).
3. Before the first deploy completes, Render will prompt for every env var
   marked `sync: false` in `render.yaml`. Fill in:
   - `FERNET_KEYS` — generate with:
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   - `ANTHROPIC_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
     `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
   - `RAW_WIRE_ROD_COST_PER_KG`, `PROCESSING_OVERHEAD_PER_KG` — the real
     numbers from step 0, not the repo's example defaults (62.0 / 18.0).
   - `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` — leave blank for now, you'll
     come back to these in steps 2b and 4.
4. Deploy. `preDeployCommand: alembic upgrade head` runs the real migration
   against real Postgres before the new instance takes traffic.
5. Once live, copy the assigned URL (`https://nailfactory-backend-xxxx.onrender.com`).

### 2b. Set ALLOWED_HOSTS now

In the backend service's **Environment** tab, set:
```
ALLOWED_HOSTS=nailfactory-backend-xxxx.onrender.com
```
(the hostname only, no `https://`). Add a custom domain here too if you
attach one later. Redeploy for it to take effect — until this is set
correctly, every request 400s at `TrustedHostMiddleware` (that's it working
as intended, not a bug).

## 3. Deploy the frontend on Vercel

1. Vercel dashboard → **Add New** → **Project** → import this repo.
2. Set **Root Directory** to `frontend`.
3. Environment variables:
   ```
   NEXT_PUBLIC_API_BASE_URL=https://nailfactory-backend-xxxx.onrender.com
   NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_...
   NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_live_...
   ```
4. Deploy. Vercel gives you a `*.vercel.app` URL immediately; attach a
   custom domain under Project Settings → Domains whenever you have one.

`next.config.mjs`'s `rewrites()` proxies `/api/*` to
`NEXT_PUBLIC_API_BASE_URL` in production exactly as it does locally — the
browser only ever talks to your Vercel domain, which is what keeps the
`SameSite=Strict` refresh cookie working without loosening it to `None`.

## 4. Close the loop: CORS

Back on Render, set:
```
CORS_ALLOWED_ORIGINS=https://your-project.vercel.app,https://your-custom-domain.com
```
(comma-separated, both if you have a custom domain pointed at Vercel).
Redeploy the backend. Until this matches the real frontend origin exactly,
any request that isn't proxied through the Next.js rewrite (there
shouldn't be any in normal use, but e.g. a future mobile app or direct API
integration would need it) gets rejected by CORS.

## 5. Register payment webhooks

- **Stripe** dashboard → Developers → Webhooks → Add endpoint:
  `https://nailfactory-backend-xxxx.onrender.com/api/v1/webhooks/stripe`.
  Copy the signing secret it gives you into Render's `STRIPE_WEBHOOK_SECRET`.
- **Razorpay** dashboard → Settings → Webhooks → Add:
  `https://nailfactory-backend-xxxx.onrender.com/api/v1/webhooks/razorpay`.
  Copy the secret into `RAZORPAY_WEBHOOK_SECRET`.

Redeploy the backend after either changes.

## 6. Verify the live deployment

```bash
curl https://nailfactory-backend-xxxx.onrender.com/health          # {"status":"ok"}
curl -i https://nailfactory-backend-xxxx.onrender.com/docs         # expect 404 — EXPOSE_API_DOCS=false in render.yaml
```

Then, in a browser, visit the Vercel URL and walk the real buyer path:
register → submit an RFQ → (as a real staff account, see step 7) issue and
approve a quote → accept it → confirm the 30/70 milestones appear. This is
the same path verified locally against SQLite/fakeredis during
development — running it once against the real deploy is what confirms
Postgres, Redis, and the payment providers are actually wired correctly.

## 7. Create your first real staff account

`scripts/seed.py`'s demo `SalesManager` account (`manager@nailfactory.example`)
is **deliberately never created** when `ENFORCE_HTTPS=true` (which
`render.yaml` sets) — its password is public in this repo's history, so it
must never exist in production. There is currently no self-serve "become
staff" flow (`POST /auth/register` always creates a `ClientProcurement`
buyer account), so provision the first `SalesManager`/`SalesRep` by hand:
connect to the Render Postgres shell (Render dashboard → your database →
Connect) and run something like:

```sql
UPDATE users SET role = 'SalesManager' WHERE email = 'you@yourcompany.com';
```

(register that email as a normal buyer first through the UI, then run the
`UPDATE` — this reuses the existing password-hashing path instead of
inserting a hash by hand).

## Go-live checklist

- [ ] 2FA enabled on GitHub, Render, Vercel, Stripe, Razorpay, and the
      Anthropic console — these are now custody of real money and PII.
- [ ] Confirm the demo manager login fails: it should, per step 7.
- [ ] Confirm `/docs` and `/openapi.json` both 404 on the live backend URL.
- [ ] In the Render dashboard, confirm both `nailfactory-postgres` and
      `nailfactory-redis` show an empty IP allow list (private-network only).
- [ ] Replace the demo catalog (`scripts/seed.py`'s five example SKUs) with
      the real product line, either through direct SQL or a customized
      seed script — the demo catalog's rows aren't security-sensitive
      (only the manager-account block is guarded), so re-running
      `scripts.seed` in production for catalog data alone is safe.
- [ ] Set up billing alerts on Render, Vercel, Stripe, and Anthropic —
      the negotiation agent and rate limiter bound abuse, but not cost
      surprises from legitimate traffic growth.
- [ ] Set up an uptime monitor (e.g. UptimeRobot, Better Uptime) polling
      `/health`.
- [ ] Restrict who on your team has Render/Vercel/Stripe/Razorpay dashboard
      access to those who actually need it.
- [ ] Confirm Render's automated Postgres backups are enabled and note the
      retention window for your plan.
- [ ] Review data-protection obligations for your buyers' jurisdictions
      (GSTIN/PII is stored encrypted at rest via Fernet, but retention and
      breach-notification policy is a business decision, not a code one).

## Rolling back

- **Render**: the service's **Events** tab lists every deploy; "Rollback"
  on a previous one redeploys that exact image immediately.
- **Vercel**: the **Deployments** tab lets you instantly "Promote to
  Production" any previous build — no rebuild needed.

## Adding future database migrations

```bash
cd backend
# after changing app/models/models.py:
alembic revision --autogenerate -m "describe the change"
# inspect the generated file in migrations/versions/ before committing —
# in particular, re-check that no new EncryptedString column slipped past
# the render_item hook in migrations/env.py (it should render as sa.Text()).
git add migrations/versions/ && git commit -m "..."
git push
```

CI (`.github/workflows/ci.yml`, `migrations` job) applies the new migration
to a real throwaway Postgres container on every push — if that job is
green, `preDeployCommand: alembic upgrade head` will apply cleanly on Render
too.
