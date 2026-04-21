# onec-mcp-universal Audit Report

Date: 2026-04-12

## Executive Summary
- Baseline tests: `377 passed` (local run after fixes).
- CI now enforces coverage via `pytest-cov` gate (`line+branch >= 60%`).
- Main architectural hotspot: monolithic dashboard/server modules with mixed concerns.

## Findings

### Correctness
- Fixed: `gateway/tests/test_server.py` had stale expectations for `/api/export-bsl` after BSL workspace validation changes.
- Risk: export API behavior is sensitive to environment-dependent settings (`bsl_host_workspace`, `bsl_workspace`).

### Testing & Coverage
- Strong unit surface already exists (`377` collected tests).
- Prior CI lacked measurable coverage enforcement; fixed in `.github/workflows/ci.yml`.
- Remaining risk: local environment cannot compute coverage in this host due missing `pytest-cov`; CI is now source of truth.

### Architecture
- `gateway/gateway/web_ui.py` and `gateway/gateway/server.py` remain large and combine rendering, route handlers, and orchestration logic.
- `gateway/gateway/mcp_server.py` central dispatch is broad and hard to reason about as a single unit.

### Dashboard UX/Usability
- Current dashboard is functional and bilingual, but relies on large inline HTML/CSS/JS templates.
- UX risks:
  - High maintenance cost for visual/interaction regressions.
  - Limited component-level testability.
  - Potential inconsistency across desktop/mobile refinements as feature count grows.

### Security
- Existing tests include escaping checks and endpoint behavior; no immediate high-severity issue found in this pass.
- Should continue negative-path testing on all dashboard mutating endpoints.

### Performance / Load
- No deterministic load benchmark suite in repo yet.
- Session cleanup and background export logic should be load-tested with concurrent API traffic.

## Immediate Actions Completed
- Updated failing export API tests to patch current `settings` usage.
- Added CI coverage gate:
  - `--cov=gateway --cov-branch --cov-fail-under=60`
