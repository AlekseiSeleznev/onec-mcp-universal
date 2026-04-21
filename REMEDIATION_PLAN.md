# onec-mcp-universal Remediation Plan

Date: 2026-04-12

## P0
1. Keep CI green under the new coverage gate (`line+branch >= 60%`) and close uncovered branches surfaced by GitHub Actions.
2. Add integration tests for `/api/export-bsl` covering:
   - missing workspace config,
   - duplicate running exports,
   - cancelled jobs,
   - output path derivation from `Ref=`.

## P1
1. Split dashboard module into:
   - `web_ui/routes.py`,
   - `web_ui/templates.py`,
   - `web_ui/services.py`.
2. Extract shared API response helpers for consistent error contracts.
3. Add dashboard API contract tests (shape + status code matrix).

## P2
1. Add load smoke suite for:
   - concurrent `/mcp` calls,
   - parallel export-status polling,
   - session cleanup under active traffic.
2. Introduce lightweight UX regression checklist (mobile, keyboard, language switch).

## Acceptance Criteria
- CI passes with current threshold and no regressions in covered branches.
- No flaky tests across 3 consecutive CI runs.
- Dashboard refactor preserves API behavior and language parity.
