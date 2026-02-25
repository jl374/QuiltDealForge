# DealForge

Quilt Capital's internal platform for AI-powered deal sourcing, CRM, and outreach automation.

---

## Prerequisites

- [Node.js 20+](https://nodejs.org/)
- [Python 3.12](https://www.python.org/) (`brew install python@3.12`)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for local Postgres)

---

## First-Time Setup

### 1. Clone and install

```bash
git clone <repo>
cd QuiltDealForge

# Install frontend deps
npm install

# Set up Python virtualenv for the API
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ../..
```

### 2. Configure environment variables

```bash
# Root .env (used by docker-compose)
cp .env.example .env

# Frontend
cp apps/web/.env.example apps/web/.env.local
# Edit apps/web/.env.local — fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, NEXTAUTH_SECRET, INTERNAL_API_KEY

# Backend
cp apps/api/.env.example apps/api/.env
# Edit apps/api/.env — fill in INTERNAL_API_KEY (must match frontend)
```

Generate secrets:
```bash
# NEXTAUTH_SECRET
openssl rand -base64 32

# INTERNAL_API_KEY
openssl rand -hex 32
```

### 3. Google OAuth setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project: "DealForge"
3. Enable Google+ API
4. Create OAuth 2.0 credentials (Web application)
5. Add authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
6. Copy Client ID and Client Secret to `apps/web/.env.local`

### 4. Start the database

```bash
docker compose up -d
```

### 5. Run migrations

```bash
cd apps/api
source .venv/bin/activate
alembic upgrade head
```

### 6. Seed sample data (optional)

```bash
python seed.py
```

---

## Running Locally

Open two terminals:

**Terminal 1 — Frontend**
```bash
npm run dev:web
# → http://localhost:3000
```

**Terminal 2 — Backend**
```bash
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs (Swagger UI)
```

---

## Project Structure

```
QuiltDealForge/
├── apps/
│   ├── web/          # Next.js 15 frontend
│   └── api/          # FastAPI backend
├── infra/            # Docker and infrastructure configs
├── docker-compose.yml
└── README.md
```

---

## Environment Variables

### `apps/web/.env.local`

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `NEXTAUTH_SECRET` | Random secret for session signing (openssl rand -base64 32) |
| `NEXTAUTH_URL` | `http://localhost:3000` |
| `API_BASE_URL` | `http://localhost:8000` |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` |
| `INTERNAL_API_KEY` | Shared secret between Next.js and FastAPI |

### `apps/api/.env`

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `INTERNAL_API_KEY` | Must match `INTERNAL_API_KEY` in frontend |
| `ALLOWED_ORIGINS` | CORS: `http://localhost:3000` |
| `ANTHROPIC_API_KEY` | Phase 2+ |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL 16 |
| Auth | NextAuth.js v4, Google OAuth (quilt-cap.com only) |
| AI (Phase 2+) | Anthropic Claude API |

---

## Build Roadmap

| Phase | Timeline | Focus |
|---|---|---|
| 0 (current) | Weeks 1–2 | Auth, DB schema, company list + add form |
| 1 | Weeks 3–6 | Pipeline Kanban, activity log, tasks, Gmail sync |
| 2 | Weeks 7–10 | Email templates, AI drafting (Claude), outreach sequences |
| 3 | Weeks 11–14 | Contact enrichment (Apollo), AI Fit Score, pre-meeting briefs |
| 4 | Weeks 15–18 | Google Calendar, DiligenceForge handoff, analytics |
| 5 | Weeks 19–24 | LinkedIn outreach, A/B testing, mobile polish |
