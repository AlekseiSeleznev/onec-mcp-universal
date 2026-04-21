# Session Management (Workflow Layer P1)

`session-*` skills add portable continuity for long 1C development sessions.

## Commands

- `/session-save` — writes/updates `session-notes.md` with deterministic sections
- `/session-restore` — restores context from `session-notes.md` and continues from `Next Action`
- `/session-retro` — appends short retrospective block to `session-notes.md`

## Canonical file

Project root file: `session-notes.md`

Required sections:

- `## Current Task`
- `## Completed`
- `## Pending`
- `## Next Action`
- `## Key Decisions`
- `## Modified Files`

## Rules

- `Next Action` must be concrete and executable.
- `Completed` contains only done work, no plans.
- `session-restore` treats notes as context, not immutable requirements.

## Context guard integration

Use monitor scripts to warn about context growth during long sessions:

- `tools/context-monitor.sh` (Linux/macOS)
- `tools/context-monitor.ps1` (Windows)

Warning thresholds:

- 70%: recommendation to run `/session-save`
- 85%: urgent recommendation to run `/session-save`
