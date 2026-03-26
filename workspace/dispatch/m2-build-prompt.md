You are building an autonomous task dispatch system across two repos. Follow the implementation plan exactly, task by task. Commit after each task.

## Repos

- **jimbo-api:** ~/development/jimbo/jimbo-api (Hono/TypeScript, better-sqlite3, Vitest)
- **openclaw:** ~/development/openclaw (Python scripts, stdlib only)

## Plan Location

Read the full plan at: ~/development/openclaw/docs/superpowers/plans/2026-03-25-autonomous-dispatch.md

## Your Scope

Execute **Tasks 1, 2, 3, 4, 6, and 7** from the plan. Skip Tasks 5, 8, 9, 10 (those involve VPS deployment and will be done manually).

## Execution Order

1. **Task 1** — Create `src/types/dispatch.ts` in jimbo-api. Commit.
2. **Task 2** — Add dispatch_queue table migration + vault field migrations in jimbo-api `src/db/index.ts`. Update vault types and service. Run existing tests to verify nothing broke. Commit.
3. **Task 3** — Create `test/dispatch.test.ts` and `src/services/dispatch.ts` in jimbo-api. Run tests until green. Commit.
4. **Task 4** — Create `src/routes/dispatch.ts` in jimbo-api. Mount in `src/index.ts`. Handle the public approval-link routes (they need to bypass auth middleware — mount them before the `app.use('/api/*', apiKeyAuth)` line). Run all tests. Commit.
5. **Task 6** — Create prompt templates in openclaw `workspace/dispatch/templates/` (coder.md, researcher.md, drafter.md). Commit.
6. **Task 7** — Create `workspace/dispatch.py` and `workspace/tests/test_dispatch.py` in openclaw. Run Python tests. Commit.

## Critical Patterns to Follow

### jimbo-api patterns
- Routes are thin (parse input, validate, call service, return response)
- Services do all DB work via `getDb()` singleton
- Types are in separate files under `src/types/`
- Migrations use try/catch to ignore "already exists" errors
- Tests use Vitest, isolated DB via `process.env.CONTEXT_DB_PATH`
- Auth middleware is at `src/middleware/auth.ts` — applied to `/api/*`
- Conventional commits: `feat:`, `fix:`, `test:`, `chore:`

### openclaw patterns
- Python scripts are stdlib only (no pip)
- Scripts default to dry-run, `--live` flag for writes
- Telegram notifications via Bot API (fire-and-forget, silent if env vars missing)
- jimbo-api calls via urllib.request with X-API-Key header
- Tests in workspace/tests/ using unittest

### Both repos
- Never use `vi.mock()` — use builder functions for test setup
- Read the plan for exact code — it has complete implementations

## Before You Start

1. Read the full plan file at the path above
2. Read the spec at ~/development/openclaw/docs/superpowers/specs/2026-03-25-autonomous-dispatch-design.md for architectural context
3. Check the current state of jimbo-api: read `src/db/index.ts` (schema), `src/index.ts` (route mounting), `src/types/vault.ts` (existing vault types), and `src/services/vault.ts` (vault service patterns)

## After Each Task

1. Run the relevant test suite (`npm test` for jimbo-api, `python3 -m unittest` for openclaw)
2. Fix any failures before moving on
3. Commit with a conventional commit message
4. Move to the next task

## When You're Done

Print a summary of what was completed, any issues encountered, and what's ready for manual deployment (Tasks 5, 8-10).
