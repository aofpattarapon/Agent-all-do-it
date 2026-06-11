# PROJECT_STATE — pixel_dream_agent

## Quick Facts
- **Path**: `~/Desktop/Web-app-agent-Kimi/pixel_dream_agent`
- **Backend**: `http://localhost:8100` (Docker FastAPI)
- **Frontend**: `http://localhost:3100` (Next.js 15 + React Query + Tailwind)
- **Ports**: Postgres `5433→5432`, Redis `6380→6379`, Flower `5556`
- **Admin**: `admin@example.com` / `admin123`

## Stack
- **Backend**: FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery, Alembic
- **Frontend**: Next.js 15, React Query, Tailwind
- **Networking**: Frontend `/api/*` → Next.js proxy → Backend
- **Auth**: Cookie-based (`access_token`=15min, `refresh_token`=7d) with auto-refresh

## Features Done
- [x] Agent Template Catalog (46 templates from Agency-Agents + 500-AI-Agents repos)
- [x] Skill Catalog (37 skills, 15 categories) — backend + frontend selector
- [x] Auto token refresh on 401
- [x] Admin user + login fix
- [x] Template popup scrolling fix
- [x] **Expand Model/Runtime Options** — added Codex CLI, Kimi CLI, OpenAI API to frontend + backend adapters
- [x] **Model Selector** — per-runtime model dropdown (Sonnet, Opus, GPT-5.4, o4-mini, etc.)
- [x] **Fix Project Page Layout** — changed `max-w-4xl` → `max-w-7xl` on projects list + project detail
- [x] **Knowledge Base Catalog** — 12 curated templates, backend API, frontend import UI in Knowledge tab
- [x] **Settings Sub-Menus** — expandable Settings sidebar with Profile, Account, Appearance, Console
- [x] **Tutorial/Onboarding Page** — `/tutorial` with quick-start guide and pro tips

## Active Tasks
- None — all 5 requested features completed

## Key Conventions
- Backend endpoints need matching Next.js `/api/*` proxy route
- Public catalogs (templates, skills, knowledge-templates) proxies = no auth required
- Project/agent APIs = require `access_token` cookie
- All backend DB models use `TimestampMixin`
- Frontend `apiClient` uses `credentials: "include"`
- Alembic `env.py` imports `from app.db.models import *` to ensure all models registered

## Database
- Latest migration: `55c3dc1dbae0` (add_knowledge_templates)
- Previous head merge: `74892eba7c77` (merge_heads) — stamped over, not in local files
- Watch for head conflicts when creating new migrations

## Seed Commands
```bash
# Agent templates
docker compose exec app python cli/commands.py cmd seed-templates --clear

# Skills
docker compose exec app python cli/commands.py cmd seed-skills --clear

# Knowledge templates
docker compose exec app python cli/commands.py cmd seed-knowledge-templates --clear
```

## New Backend Files
- `backend/app/db/models/knowledge_template.py`
- `backend/app/schemas/knowledge_template.py`
- `backend/app/repositories/knowledge_template.py`
- `backend/app/services/knowledge_template.py`
- `backend/app/api/routes/v1/knowledge_templates.py`
- `backend/app/commands/seed_knowledge_templates.py`
- `backend/app/services/runtime/kimi_cli.py`
- `backend/app/services/runtime/openai_api.py`

## New Frontend Files
- `frontend/src/hooks/use-knowledge-templates.ts`
- `frontend/src/app/api/knowledge-templates/route.ts`
- `frontend/src/app/api/knowledge-templates/categories/route.ts`
- `frontend/src/app/api/knowledge-templates/[[...id]]/route.ts`
- `frontend/src/app/[locale]/(dashboard)/tutorial/page.tsx`

## Modified Key Files
- `frontend/src/app/[locale]/(dashboard)/projects/page.tsx` — layout width
- `frontend/src/app/[locale]/(dashboard)/projects/[id]/page.tsx` — runtime options, model selector, knowledge catalog
- `frontend/src/components/console/ConsoleShell.tsx` — settings submenu, tutorial nav
- `backend/app/services/runtime/__init__.py` — registered new adapters
- `backend/alembic/env.py` — model imports
- `docker-compose.yml` — added alembic volume mount

## Blockers
- None
