# Report Full Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make report execution self-healing enough to analyze reports lazily on first use, refresh catalogs after BSL lifecycle events, and provide a repeatable job for validating every cataloged report in ERP_DEMO and Z01.

**Architecture:** Keep static report discovery in `report_analyzer.py`, persistent state in `report_catalog.py`, execution code generation in `report_runner.py`, and MCP/HTTP orchestration in `tool_handlers/reports.py`. Add lazy catalog refresh before single-report execution and a bulk validation API/tool that records every attempted run with strategy/error diagnostics instead of hiding unsupported reports.

**Tech Stack:** Python 3.12, Starlette HTTP facade, MCP tool handlers, SQLite catalog, pytest, 1C toolkit `execute_code`.

---

### Task 1: Lazy Analyze Before Single Report Execution

**Files:**
- Modify: `gateway/gateway/tool_handlers/reports.py`
- Modify: `gateway/gateway/report_catalog.py`
- Test: `gateway/tests/test_tool_handlers_reports.py`
- Test: `gateway/tests/test_report_catalog.py`

- [ ] **Step 1: Write failing tests**

Add tests that `run_report` triggers `rebuild_report_catalog_for_db_info` when the requested technical report is missing from the catalog, then retries resolution and executes the report.

- [ ] **Step 2: Verify RED**

Run: `pytest gateway/tests/test_tool_handlers_reports.py::test_run_report_lazy_analyzes_missing_catalog -q`
Expected: FAIL because `try_handle_report_tool` currently returns `report_not_found` without rebuilding the catalog.

- [ ] **Step 3: Implement lazy refresh**

Add a helper in `tool_handlers/reports.py` that calls `catalog.describe_report`; on `report_not_found` or empty catalog, call `rebuild_report_catalog_for_db_info`; then call `describe_report` again. Wire `run_report`, `describe_report`, and `explain_report_strategy` through this helper where useful.

- [ ] **Step 4: Verify GREEN**

Run: `pytest gateway/tests/test_tool_handlers_reports.py gateway/tests/test_report_catalog.py -q`
Expected: PASS.

### Task 2: Bulk Report Validation Tool/API

**Files:**
- Modify: `gateway/gateway/tool_handlers/reports.py`
- Modify: `gateway/gateway/server.py`
- Modify: `gateway/gateway/report_catalog.py`
- Test: `gateway/tests/test_tool_handlers_reports.py`
- Test: `gateway/tests/test_server_reports.py`

- [ ] **Step 1: Write failing tests**

Add `validate_all_reports` MCP tool schema and `/api/reports/validate-all` route mapping. Test that it enumerates catalog reports, analyzes first if requested, executes each executable strategy, records unsupported reports as diagnostics, and returns counts.

- [ ] **Step 2: Verify RED**

Run: `pytest gateway/tests/test_tool_handlers_reports.py::test_validate_all_reports_runs_every_catalog_entry -q`
Expected: FAIL because the tool does not exist.

- [ ] **Step 3: Implement minimal synchronous validator**

Add tool name `validate_all_reports`, input fields `database`, `analyze`, `max_rows`, `limit`, `strategy`, `include_unsupported`. Implement sequential execution with per-report result objects. Do not invent success for unsupported reports; return `status=unsupported` with catalog diagnostics.

- [ ] **Step 4: Verify GREEN**

Run: `pytest gateway/tests/test_tool_handlers_reports.py gateway/tests/test_server_reports.py -q`
Expected: PASS.

### Task 3: Broaden Strategy Synthesis Safely

**Files:**
- Modify: `gateway/gateway/report_analyzer.py`
- Modify: `gateway/gateway/report_runner.py`
- Test: `gateway/tests/test_report_analyzer.py`
- Test: `gateway/tests/test_report_runner.py`

- [ ] **Step 1: Write failing tests**

Add fixtures for DataCompositionSchema templates that contain safe period parameters, unknown parameters, external datasets, and exported manager entrypoints. Expected behavior: safe SKD gets `raw_skd_runner`; unknown-param SKD gets a probe-capable strategy with `requires_runtime_probe=true`; spreadsheet templates remain unsupported.

- [ ] **Step 2: Verify RED**

Run: `pytest gateway/tests/test_report_analyzer.py::test_analyzer_marks_unknown_param_skd_as_probe_strategy -q`
Expected: FAIL because the analyzer currently classifies these as unsupported/runtime-only without an executable strategy.

- [ ] **Step 3: Implement probe strategy**

Add `raw_skd_probe_runner` as a lower-confidence strategy for DataCompositionSchema templates that require runtime probing. Extend `ReportRunner._select_strategy` and code generation to run it with default/empty parameters while clearly returning runtime errors if 1C rejects missing parameters.

- [ ] **Step 4: Verify GREEN**

Run: `pytest gateway/tests/test_report_analyzer.py gateway/tests/test_report_runner.py -q`
Expected: PASS.

### Task 4: Live Analyze And Full Execution Attempt

**Files:**
- No source edits unless live failures identify fixable runner/analyzer bugs.
- Runtime data: `/var/lib/docker/volumes/onec-mcp-universal_gw-data/_data/report-catalog.sqlite`

- [ ] **Step 1: Rebuild gateway**

Run: `docker compose up -d --build gateway`
Expected: gateway healthy and both databases keep `epf_connected=true`.

- [ ] **Step 2: Analyze both databases**

Run `/api/reports/analyze` for `ERP_DEMO` and `Z01`.
Expected: catalog counts remain `1120` and `343`.

- [ ] **Step 3: Validate all reports**

Run `/api/reports/validate-all` for both databases with `max_rows=5`.
Expected: every cataloged report receives a concrete status: `done`, `error`, or `unsupported`.

- [ ] **Step 4: Fix repeatable architecture bugs**

If failures are caused by generated code, strategy selection, wrong template detection, or catalog ambiguity, add failing tests and fix them. If failures are due to genuine business parameters or missing external data, keep them as report diagnostics rather than claiming success.

- [ ] **Step 5: Final verification**

Run targeted report tests and full `pytest` under `gateway/`. Record live validation totals and unresolved categories in MemPalace.

