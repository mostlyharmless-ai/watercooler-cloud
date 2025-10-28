# Repository Guidelines

## Project Structure & Module Organization
- App code lives under `src/` (components, hooks, utils). Keep features grouped by domain: `src/<feature>/` with `index.ts` as entry.
- Tests reside in `tests/` mirroring `src/` paths (e.g., `src/chat/room.ts` → `tests/chat/room.test.ts`).
- Configuration lives at repo root (e.g., `package.json`, `.eslint.*`, `.prettier*`, `tsconfig.json`). Static assets (images, styles) go under `assets/`.

## Build, Test, and Development Commands
- `npm install` — install dependencies.
- `npm run dev` — start local development server with hot reload.
- `npm run build` — produce optimized production build to `dist/`.
- `npm test` — run unit tests in watchless/CI mode.
- `npm run lint` — lint codebase; add `--fix` to auto‑fix.

## Coding Style & Naming Conventions
- TypeScript preferred in `*.ts`/`*.tsx`. Use ES modules.
- Indentation: 2 spaces; max line length per Prettier.
- Naming: files kebab-case (`message-list.tsx`), React components PascalCase, non-component modules camelCase.
- Enforce formatting with Prettier (`npm run format`) and lint with ESLint (airbnb/ts rules). No unused exports; prefer explicit types at public boundaries.

## Testing Guidelines
- Test framework: Jest + @testing-library (for React) or Node testing utils where applicable.
- Test files use `*.test.ts`/`*.test.tsx`; co-locate in `tests/` mirroring paths.
- Aim for meaningful coverage on core logic and integrations; avoid brittle snapshot-only tests.
- Run all tests: `npm test`. Single file: `npm test -- tests/chat/room.test.ts`.

## Commit & Pull Request Guidelines
- Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`). Scope optional (e.g., `feat(chat): ...`).
- Keep commits focused and message bodies explain the “why”.
- PRs must include: clear summary, linked issue (e.g., `Closes #123`), steps to test, and screenshots for UI changes.
- CI must pass (build, tests, lint) before merge. Prefer squash merge with a clean, conventional title.

## Security & Configuration Tips
- Never commit secrets; use environment files like `.env.local` (gitignored). Document required vars in `README`.
- Validate external input and sanitize user-rendered content. Review dependencies regularly with `npm audit`.

## Codex Watercooler Protocol (Session Rules)
- Purpose: Standardize how Codex (this assistant) uses Watercooler tools so entries remain attributable and contextually accurate.
- Pre‑flight (required before any write: say/ack/handoff/set_status):
  - Ensure Agent base is set to `Codex`.
  - Ensure a clear specialization `spec` is set to match the current task (examples below).
  - If either is missing/unclear, do not post; set/confirm first.
- Setting identity:
  - Preferred (cloud context): call `watercooler_v1_set_agent` with `base="Codex"` and an appropriate `spec` (e.g., `pm`, `planner-architecture`, `implementer-code`, `tester`, `security-audit`, `docs`, `ops`, or `general-purpose`).
  - Local context (no explicit setter): still enforce the rule by selecting the matching entry Role and adding a visible `Spec: <value>` line at the top of the entry body.
- Role alignment:
  - Keep `spec` (session specialization) and Watercooler entry `Role` distinct but aligned (e.g., `spec=pm` → Role `pm`; `planner-architecture` → Role `planner`; `implementer-code` → Role `implementer`; `docs` → Role `scribe`).
- Default taxonomy (examples):
  - `pm`, `planner-architecture`, `implementer-code`, `tester`, `security-audit`, `debugger`, `docs`, `ops`, `general-purpose`.
- Entry formatting requirement:
  - Include a first-line marker in the entry body: `Spec: <spec>` to make specialization explicit in the thread record.
- Failure policy:
  - If `base` and suitable `spec` are not set, Codex will block the write and prompt to set them before proceeding.

## Branch Pairing Contract (Team Invariant)
- Repositories: Pair each code repo with a dedicated threads repo named `<repo>-threads`.
- Branches: Mirror code branches in the threads repo (same branch name).
- Write behavior: Before a write, ensure the threads repo is on the same‑named branch; push with rebase+retry.
- Commit footer convention (in threads repo):
  - `Code-Repo: <org>/<repo>`
  - `Code-Branch: <branch>`
  - `Code-Commit: <short-sha>`
  - `Watercooler-Entry-ID: <ULID>`
  - `Watercooler-Topic: <topic>`
- Authoring: Include a visible `Spec: <value>` in the entry body and align the Role to the specialization (pm/planner/implementer/tester/docs/ops/etc.).
- Closure: On merge, post a Closure entry referencing the PR; optionally consolidate to `threads:main` with a brief summary.
