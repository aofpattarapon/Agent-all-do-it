# pixel_dream_agent — Core

FastAPI + Next.js 15 full-stack AI agent platform with crypto trading pipelines.

## Module map

- `backend/app/` — FastAPI backend (Python 3.14+, uv)
  - `api/routes/v1/` — HTTP endpoints (never call repos directly)
  - `services/` — business logic classes (`__init__(self, db)`)
  - `repositories/` — pure data access (flush/refresh, never commit)
  - `schemas/` — Pydantic v2 `*Create / *Update / *Read / *List`
  - `db/models/` — SQLAlchemy `Mapped[]` models
  - `crypto/` — crypto trading sub-package (execution, adapters)
  - `services/run_executor.py` — the main pipeline runner (1970+ lines)
  - `services/run_trade_outcome.py` — pure trade outcome computation (new)
  - `commands/seed_crypto_workflow.py` — workflow JSON definitions + agent prompts
- `frontend/src/` — Next.js 15 App Router (TypeScript strict)
  - `app/[locale]/(dashboard)/projects/[id]/page.tsx` — main project page (runs tab)
  - `app/[locale]/(dashboard)/projects/[id]/runs/[runId]/page.tsx` — run detail
  - `components/projects/run-block-detail.tsx` — expandable block/error detail
  - `components/console/use-console-data.ts` — shared RunItem interface

## Key invariants

- Routes → Services → Repos (never skip layers)
- DB: async PostgreSQL (asyncpg), never `db.commit()` in repos (session auto-commits)
- Serena is TypeScript-only for this project; use Bash/Read for Python files
- `mem:tech_stack` for stack details, `mem:conventions` for code style

## Trade pipeline specifics

See `mem:crypto_pipeline` for NEXMIND agent architecture and run outcome classification.
