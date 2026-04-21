# Project Bootstrap (Workflow Layer P1)

`/1c-project-init` is a local bootstrap helper for projects using `onec-mcp-universal`.

## What it does

1. Detects target project path (argument or current directory)
2. Checks base project structure
3. Copies `templates/mcp.json` to `<project>/.mcp.json` if missing
4. Creates `session-notes.md` template if missing
5. Reports created/skipped/manual steps

## What it does not do

- No direct infra provisioning
- No automatic server deployment
- No `1cv8`/DESIGNER execution
- No secret persistence

## Template details

`templates/mcp.json` includes:

- `onec-universal` (default)
- `onec-bsl-graph` (optional)
- `onec-test-runner` (optional)

All point to local gateway URL `http://localhost:8080/mcp`. Optional entries require enabling corresponding profiles in the gateway stack.

## Safety contract

- Existing `.mcp.json` is not overwritten.
- Skill should propose merge recommendations when project config already exists.
