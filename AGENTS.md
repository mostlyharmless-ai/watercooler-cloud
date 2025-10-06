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
