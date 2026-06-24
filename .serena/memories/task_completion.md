# Task Completion Checklist

## Backend
```bash
cd backend
uv run ruff check . --fix && uv run ruff format .
uv run pytest
uv run ty check   # type checker (optional, may have pre-existing errors)
```

## Frontend
```bash
cd frontend
bun run lint      # has 7 pre-existing errors in game files — new errors = regression
bun test
```

## DB migrations (when models change)
```bash
cd backend
uv run alembic revision --autogenerate -m "Description"
uv run alembic upgrade head
```

## Notes
- Frontend lint has 7 pre-existing errors (`@ts-nocheck` in game files, MapHelpers/Pathfinder).
  Do not count those as regressions.
- Backend ruff: 0 errors expected on all `app/` and `tests/` files.
