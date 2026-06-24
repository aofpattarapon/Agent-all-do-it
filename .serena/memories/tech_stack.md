# Tech Stack

## Backend
- Python 3.14+, uv (package manager, `uv run` for all commands)
- FastAPI + Pydantic v2, async SQLAlchemy 2 + asyncpg (PostgreSQL)
- Celery (task dispatch via subprocess, not direct publish — see runs.py `_dispatch_task`)
- Redis (broker/cache), Alembic (migrations)
- Ruff (lint + format), ty (type checker)

## Frontend
- Next.js 15 App Router, TypeScript strict mode
- Tailwind CSS, Bun (package manager + test runner)
- React Query (useQuery/useMutation), i18n built-in

## Key versions / pins
- Ruff line length: 120 chars
- SQLAlchemy models use `Mapped[T]` + `mapped_column()` (SA 2.x style)
- Pydantic v2: `ConfigDict(from_attributes=True)` on all schemas

## Commands
```bash
# Backend
cd backend && uv run uvicorn app.main:app --reload --port 8000
uv run pytest / uv run pytest tests/test_file.py -v
uv run ruff check . --fix && uv run ruff format .
uv run alembic upgrade head

# Frontend
cd frontend && bun dev / bun test / bun run lint
```
