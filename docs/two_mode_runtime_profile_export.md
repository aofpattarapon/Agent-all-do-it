# Two-Mode Runtime Profile Export

Date: 2026-06-11

This export defines a clean `test` / `production` runtime switch for the 12-agent crypto workflow.

## Modes

- `test`: low-cost or free-friendly system testing
- `production`: higher-quality runtime/model assignment

## Core Design

- one backend source of truth for runtime profiles
- one `apply-runtime-profile` command
- deterministic role-based mapping
- stored fallback chains
- stored gate policy

## Main Command

```bash
uv run pixel_dream_agent cmd apply-runtime-profile --project-id <uuid> --profile test --dry-run
uv run pixel_dream_agent cmd apply-runtime-profile --project-id <uuid> --profile production
```

## Full Plan And Prompts

See:
- `Doc implement/TWO_MODE_RUNTIME_PROFILE_PLAN_AND_PROMPTS.md`

That note includes:
- implementation plan
- test/production mapping
- Claude prompt
- Kimi 2.6 prompt
- review checklist
