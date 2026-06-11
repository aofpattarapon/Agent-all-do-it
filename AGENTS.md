# Agent Instructions — pixel_dream_agent

## Critical Rule: Maintain PROJECT_STATE.md

Every time **context compaction occurs** or after completing a **significant change**, you MUST update `PROJECT_STATE.md` before proceeding.

### What counts as "significant change"
- Creating, modifying, or deleting any project file
- Adding a new feature or API endpoint
- Fixing a bug that changes behavior
- Adding/updating a database migration
- Changing environment variables, ports, or configs
- Discovering a new blocker or resolving one
- Updating dependencies or stack

### What to update in PROJECT_STATE.md
1. **Features Done** — add `[x] description` with brief detail
2. **Active Tasks** — reorder, mark done, or add new ones
3. **Blockers** — add or remove
4. **Key Conventions** — update if patterns change
5. **Database** — note new migrations or schema changes
6. **Seed Commands** — add if new seeders created

### Compact / New Session Protocol
1. Read `PROJECT_STATE.md` first
2. Read `AGENTS.md` (this file) second
3. Ask user: "Any state change since last compact?" only if unsure
4. Continue from the highest priority **Active Task**

### Files to never forget exist
- `PROJECT_STATE.md` — dynamic project state
- `AGENTS.md` — these instructions
- `backend/app/db/models/` — all SQLAlchemy models
- `frontend/src/lib/api-client.ts` — API client with auto-refresh
- `frontend/src/app/[locale]/(dashboard)/projects/[id]/page.tsx` — main project page
