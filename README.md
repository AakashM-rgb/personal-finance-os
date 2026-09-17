# personal-finance-os

A production-ready personal finance operating system for tracking expenses, budgets, savings
goals, subscriptions, accounts, analytics, and AI-powered financial insights.

See `PRODUCT_SPEC.md` for the full product spec and `CLAUDE.md` for the engineering rules this
project follows.

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- PostgreSQL running locally (or reachable), with a dedicated application role/database created
  (see `backend/.env.example` for the expected connection string shape - never use the Postgres
  superuser for the running application)

## Backend (`backend/`)

```bash
cd backend
uv venv .venv                 # or: python -m venv .venv
uv pip install -e ".[dev]"    # or: .venv/Scripts/pip install -e ".[dev]"

cp .env.example .env          # fill in real values - .env is gitignored

.venv/Scripts/alembic upgrade head      # apply migrations to DATABASE_URL
ALEMBIC_DATABASE_URL="<test db url>" .venv/Scripts/alembic upgrade head  # and to the test DB

.venv/Scripts/python -m pytest          # run tests
.venv/Scripts/python -m ruff check app tests
.venv/Scripts/python -m mypy app

.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

## Frontend (`frontend/`)

```bash
cd frontend
npm install
cp .env.example .env.local    # points at the backend, defaults to http://localhost:8000
                               # (must share a hostname with the frontend - e.g. both
                               # `localhost` - never `127.0.0.1` here: cookies are scoped
                               # per-hostname, and the CSRF cookie has to be readable by
                               # this frontend's own JavaScript to restore a session)

npm run dev          # http://localhost:3000
npm run test         # vitest
npm run typecheck    # tsc --noEmit
npm run lint         # eslint
```

## Project layout

- `backend/` - FastAPI + SQLAlchemy (async) + Alembic. Layered `api -> services -> repositories -> models`.
- `frontend/` - Next.js (App Router) + TypeScript + Tailwind CSS.
- `PRODUCT_SPEC.md` - the product requirements.
- `CLAUDE.md` - the engineering rules and phased development plan this project follows.
