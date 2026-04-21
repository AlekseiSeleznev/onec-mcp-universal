# onec-mcp-universal Workflow Layer Design

Date: 2026-04-13  
Status: implemented incrementally across the `v1.3.x`-`v1.7.x` line

## 1. Goal

Add a workflow/UX layer on top of the existing technical base of `onec-mcp-universal` without creating a parallel stack.

Principle:
- Keep current MCP toolchain as source of truth.
- Add orchestration skills, onboarding bootstrap, and session ergonomics.
- Avoid duplicating existing technical capabilities (BSL graph/search/query validation/ITS/anonymization/etc).

## 2. Current State vs External Dev Kit

### Already strong in `onec-mcp-universal`
- Core MCP tool coverage for 1C runtime operations.
- Multi-DB session routing, dashboard, optional backends (`bsl-graph`, `test-runner`).
- BSL write/reindex/search, query validation, rights analysis, ITS search, anonymization.
- 96 production skills in `skills/` (current set, including P1 + P2 additions and compatibility aliases).

### Missing (or weak) workflow layer
- Consolidated entrypoints (`expert` aliases) for lower cognitive load.
- Project bootstrap skill + ready template config.
- Session continuity skills and context-usage guard.
- Feature-level orchestration skill (`1c-feature-dev`) adapted to this repo.

Important finding:
- In the inspected external repo, `1c-feature-dev` is referenced in docs but no standalone `SKILL.md` implementation was found in `skills/`.
- Therefore, design below treats it as a new native implementation for `onec`, not a direct port.

## 3. Scope

### P1 (must)
1. Expert-skill aliases:
- `epf-expert`
- `erf-expert`
- `mxl-expert`
- `inspect`
- `validate`

2. Project bootstrap:
- `1c-project-init`
- `templates/mcp.json` (our stack preset)

3. Context guard:
- `tools/context-monitor.ps1`
- `tools/context-monitor.sh`
- docs with hook examples for Codex-compatible clients

4. Session continuity:
- `session-save`
- `session-restore`
- `session-retro`

### P2 (implemented)
1. `1c-query-opt` (workflow-oriented optimization skill, not replacing technical query tooling)
2. `1c-feature-dev` (native orchestrator for feature lifecycle in onec stack)
3. `brainstorm`
4. `write-plan`
5. `openspec-proposal`
6. `openspec-apply`
7. `openspec-archive`
8. `1c-help-mcp`
9. `bsp-patterns`
10. `img-grid`
11. `role-expert`
12. `subsystem-expert`
13. `subagent-dev`
14. `1c-test-runner`
15. `1c-web-session`
16. `playwright-test`

## 4. Design Decisions

### 4.1 Expert aliases are orchestration-only

Each alias skill:
- asks intent in one short step,
- routes user to existing granular skills,
- does not duplicate implementation logic.

Example `epf-expert` operations map:
- `init` -> `epf-init`
- `build` -> `epf-build`
- `dump` -> `epf-dump`
- `form` changes -> `epf-add-form`
- BSP registration/commands -> `epf-bsp-init`, `epf-bsp-add-command`
- validation -> `epf-validate`

Same approach for `erf-expert`, `mxl-expert`, `inspect`, `validate`.

### 4.2 `1c-project-init` is bootstrap, not deployment engine

Responsibilities:
- scaffold local assistant helper artifacts (if absent),
- generate local `mcp.json` preset for onec stack,
- generate project quick-reference file with canonical commands,
- optionally run sanity checks (available MCP endpoints, expected folders).

Non-goals:
- no direct server-side provisioning,
- no mandatory remote infra automation,
- no requirement for client-specific flows.

### 4.3 Context guard is advisory and local-only

Design:
- hook reads tool output size and estimates token pressure,
- emits warnings at `70%` and `85%`,
- never blocks execution and never mutates project files by itself.

Cross-platform:
- PowerShell script + POSIX shell script with same thresholds and message format.

### 4.4 Session skills write a simple portable artifact

Canonical artifact:
- `session-notes.md` in project root.

Contracts:
- `session-save`: overwrite/create deterministic structure.
- `session-restore`: load and continue from `Next Action` when concrete.
- `session-retro`: append short retrospective section.

### 4.5 `1c-feature-dev` is rebuilt natively for onec

Because an external concrete implementation is unavailable, we define a native one:

Phases:
1. Problem framing
2. Scope and constraints
3. Capability mapping to existing onec tools/skills
4. Data model and metadata impacts
5. Integration and migration impacts
6. Validation and rollback strategy
7. Atomic task plan
8. Execution guidance (skill/tool sequence)
9. Completion checklist

Rules:
- tool/skill-first (reuse existing onec stack),
- no speculative infra steps,
- no hidden side effects,
- explicit acceptance criteria per phase.

## 5. File-Level Blueprint

Additions under repo root:

- `skills/epf-expert/SKILL.md`
- `skills/erf-expert/SKILL.md`
- `skills/mxl-expert/SKILL.md`
- `skills/inspect/SKILL.md` (or extend existing if already present in another namespace)
- `skills/validate/SKILL.md`
- `skills/1c-project-init/SKILL.md`
- `skills/session-save/SKILL.md`
- `skills/session-restore/SKILL.md`
- `skills/session-retro/SKILL.md`
- `skills/brainstorm/SKILL.md`
- `skills/write-plan/SKILL.md`
- `skills/openspec-proposal/SKILL.md`
- `skills/openspec-apply/SKILL.md`
- `skills/openspec-archive/SKILL.md`
- `skills/1c-query-opt/SKILL.md` (P2)
- `skills/1c-feature-dev/SKILL.md` (P2)
- `skills/1c-help-mcp/SKILL.md`
- `skills/bsp-patterns/SKILL.md`
- `skills/img-grid/SKILL.md`
- `skills/role-expert/SKILL.md`
- `skills/subsystem-expert/SKILL.md`
- `skills/subagent-dev/SKILL.md`
- `skills/1c-test-runner/SKILL.md`
- `skills/1c-web-session/SKILL.md`
- `skills/playwright-test/SKILL.md`

Additions for bootstrap/ops:
- `templates/mcp.json`
- `tools/context-monitor.ps1`
- `tools/context-monitor.sh`

Documentation:
- `docs/workflow-layer-design.md` (this file)
- `docs/session-management.md` (P1 delivery doc)
- `docs/project-bootstrap.md` (P1 delivery doc)

README updates (P1 implementation phase):
- Add section `Workflow Layer` with new skills and usage.
- Add section `Context Guard` with hook setup snippets.

## 6. Skill Contracts (P1)

### `epf-expert` / `erf-expert` / `mxl-expert`
- Input: user intent in natural language.
- Output: selected operation + delegated skill call sequence.
- Validation: operation-specific existing validator skill must be called before completion.

### `inspect`
- Input: object type + path/name.
- Output: normalized call to relevant existing `*-info` style capability.
- Validation: if object unresolved, return explicit ambiguity options.

### `validate`
- Input: object category + target.
- Output: normalized call to specific validation skill(s).
- Validation: returns pass/fail with concise reason and next action.

### `1c-project-init`
- Input: optional target path.
- Output:
  - initialized helper files,
  - generated `templates/mcp.json` copy for project,
  - bootstrap report (what created/skipped).
- Validation:
  - expected files exist,
  - paths are normalized,
  - no overwrite without explicit flag/confirmation instruction in skill flow.

### `session-save` / `session-restore` / `session-retro`
- Input: current conversation context.
- Output: deterministic `session-notes.md` sections.
- Validation: required headings present, non-empty `Next Action`.

## 7. Risks and Mitigations

1. Risk: alias skills become shallow wrappers with no value.  
Mitigation: enforce intent normalization + operation disambiguation + validator call.

2. Risk: `1c-project-init` drifts into fragile infra automation.  
Mitigation: keep bootstrap local/scaffold-only in P1.

3. Risk: context monitor spam/noise.  
Mitigation: two thresholds only, brief messages, no hard stop.

4. Risk: `1c-feature-dev` becomes verbose prompt with weak execution value.  
Mitigation: phase outputs are structured and mapped to concrete onec tools/skills.

## 8. Acceptance Criteria

P1 accepted when:
1. New alias/session/bootstrap skills exist and are documented.
2. `templates/mcp.json` reflects onec stack defaults.
3. Context guard scripts exist for both PowerShell and POSIX shells.
4. README documents new workflow features.
5. Existing tests remain green; add focused tests/docs checks where feasible.

P2 accepted when:
1. `1c-query-opt` and `1c-feature-dev` are implemented with onec-specific mappings.
2. At least one end-to-end example demonstrates feature lifecycle using current onec stack (`docs/feature-lifecycle-example.md`).
3. No duplication of existing low-level skills/tools.
4. Process skill layer (`brainstorm`, `write-plan`, `openspec-*`) is documented and executable.
