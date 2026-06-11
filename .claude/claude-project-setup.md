---
description: Investigate this project and scaffold (or upgrade) a high-quality .claude setup — CLAUDE.md, permission settings, and optional workflow commands. Stays read-only until it shows a plan.
argument-hint: [optional notes: stack, goals, anything non-obvious]
---

# Bootstrap the .claude setup for this project

You are setting up Claude Code for this repository so future sessions are fast,
safe, and need minimal hand-holding. Work in three passes — **investigate**, then
**confirm**, then **write**. Do not create or modify any file until I approve the plan.

## 1. Investigate (read-only)

Detect, don't assume. Inspect the actual repo:

- **Stack & tooling:** language(s), framework(s), package manager + lockfile,
  runtime/version files (`.nvmrc`, `.python-version`, `go.mod`, etc.), and monorepo
  layout (workspaces, `packages/`, `apps/`).
- **Real commands:** read `package.json` scripts / `Makefile` / `justfile` / task
  runner configs and note the actual dev, build, test, lint, typecheck, and format
  commands. Only list commands that genuinely exist — never invent them.
- **Conventions:** linter/formatter config, tsconfig strictness, import style,
  directory patterns, naming, how modules/features are structured.
- **Existing config to respect or mirror:** any current `.claude/`, `CLAUDE.md`,
  `.cursor/rules`, `.editorconfig`, `CONTRIBUTING.md`, or CI workflows. If a
  `.claude/` setup already exists, plan to **improve it in place**, not replace it.
- **Gotchas:** anything non-obvious a new contributor (or AI) would get wrong —
  required env vars, services that must be running, codegen, migrations.

If the repo is empty or brand new, ask me for the intended stack, purpose, and key
commands instead of guessing, and mark anything unknown as `TODO` in the output.

## 2. Show the plan, then wait

Summarize what you found (stack, commands, conventions, anything risky) and list
exactly which files you'll create or edit and why. Then STOP and wait for my
go-ahead. If anything is ambiguous, ask — one focused round of questions, not a
stream of prompts. (If I told you to skip confirmation, go straight to step 3.)

## 3. Write the setup (after approval)

### `CLAUDE.md` (project root)

High-signal and concise — it loads into every session, so no filler and no generic
advice the model already knows. Capture only project-specific knowledge:

- One-line project overview
- Tech stack and runtime versions
- Repo layout: where the important things live
- Commands: dev / build / test / lint / typecheck / format (verified, copy-pasteable)
- Conventions & patterns to follow, and anti-patterns to avoid
- Testing approach: how to run a single test, where tests live
- Guardrails: what NOT to touch, how secrets are handled, anything dangerous
- Gotchas / setup steps that aren't obvious

Keep it to roughly one screen. If a shared engineering doc already exists,
reference/import it rather than duplicating it.

### `.claude/settings.json` (committed, team-shared)

Permission rules using **prefix patterns**, never full exact command strings:

- `allow`: only safe, repetitive commands you actually saw in this repo — e.g.
  `Bash(<pkg-manager> install:*)`, `Bash(npm run:*)`, `Bash(<test-runner>:*)`,
  and read-only inspectors. Prefer relative globs (`./**`) over hardcoded
  absolute or home-directory paths.
- `deny`: destructive or sensitive operations — `Bash(rm -rf:*)`,
  `Bash(git push --force:*)`, `Bash(sudo:*)`, and secret reads like
  `Read(./**/.env*)`, `Read(./**/secrets/**)`.
- Leave anything that mutates remote state, runs arbitrary containers, or edits
  files in place (`docker run`, `gh pr create`, `sed -i`) to prompt — do NOT
  auto-allow these.
- Optionally set a default mode (e.g. `acceptEdits`) if it fits the project, and
  explain the choice.

### Hygiene

- Ensure `.claude/settings.local.json` is in `.gitignore` — it's personal and
  auto-managed and must not be committed. Add the entry if missing.
- Never write secrets, tokens, or machine-specific absolute paths into any
  committed file.

### Optional: workflow commands

Ask whether I want starter slash commands under `.claude/commands/` (e.g. a
plan → implement → verify flow, or project-specific helpers). Only scaffold these
if I say yes, and base them on how this project actually works.

## 4. Report

List every file created or changed, summarize the permission rules in plain
English, and flag anything I should review or fill in — especially `TODO`s and any
command you couldn't verify. Don't call the setup "done" while guardrails or core
commands are still unverified.
