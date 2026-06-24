# Conventions

## Python (backend)
- All route handlers return `-> Any`; `response_model=` handles serialization
- Repo functions: keyword-only args after `db`; always `flush()` + `refresh()`, never `commit()`
- Domain exceptions: `NotFoundError(message=..., details={...})` — never return None for not-found
- `datetime.now(UTC)` not `datetime.utcnow()`
- Pure/read-only service modules (no DB mutation, no LLM) live flat in `app/services/`
- Thick domains with infra → subpackage with `__init__.py` re-exporting only the facade

## TypeScript (frontend)
- `"use client"` only when component needs client-side interactivity
- Interfaces defined locally per file (not centralized) — RunItem/RunRead are duplicated across pages
- React Query for all API data fetching
- Pixel design system: `pix-pill`, `pix-frame`, `pix-row`, `pix-row-sub`, `pix-completed`, `pix-danger`, `pix-gold`, `pix-muted`

## Serena scope
- Serena is configured TypeScript-only for this project
- Use Bash/Read for Python files; use Serena symbolic tools for TypeScript files
