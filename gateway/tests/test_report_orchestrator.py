from __future__ import annotations

import pytest

from gateway.report_orchestrator import ReportEngineSettings, ReportOrchestrator


class FakeApiRunner:
    def __init__(self, result: dict):
        self.result = result
        self.calls = []

    async def run_report(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


class FakeUiRunner(FakeApiRunner):
    pass


class FakeCatalog:
    def __init__(self, policy: dict | None = None):
        self.policy = policy or {}
        self.observations = []

    def get_report_runner_policy(self, database: str, report_name: str, variant_key: str = ""):
        return dict(self.policy)

    def add_report_runner_observation(self, **kwargs):
        self.observations.append(kwargs)


@pytest.mark.asyncio
async def test_auto_uses_api_without_ui_when_api_result_matches_contract():
    api = FakeApiRunner({"ok": True, "run_id": "api-1", "contract_validation": {"matched": True}})
    ui = FakeUiRunner({"ok": True, "run_id": "ui-1"})
    catalog = FakeCatalog()

    result = await ReportOrchestrator(
        catalog=catalog,
        api_runner=api,
        ui_runner=ui,
        settings=ReportEngineSettings(api_enabled=True, ui_enabled=True, ui_fallback_enabled=True),
    ).run_report(database="ERP_DEMO", report="R", variant="", runner="auto", period=None, filters={}, params={})

    assert result["runner_used"] == "api"
    assert result["fallback_used"] is False
    assert len(api.calls) == 1
    assert ui.calls == []


@pytest.mark.asyncio
async def test_auto_falls_back_to_ui_when_api_result_is_header_only():
    api = FakeApiRunner(
        {
            "ok": True,
            "run_id": "api-1",
            "contract_validation": {"matched": False, "mismatch_code": "missing_detail_rows"},
        }
    )
    ui = FakeUiRunner({"ok": True, "run_id": "ui-1", "contract_validation": {"matched": True}})
    catalog = FakeCatalog()

    result = await ReportOrchestrator(
        catalog=catalog,
        api_runner=api,
        ui_runner=ui,
        settings=ReportEngineSettings(api_enabled=True, ui_enabled=True, ui_fallback_enabled=True),
    ).run_report(database="ERP_DEMO", report="R", variant="", runner="auto", period=None, filters={}, params={})

    assert result["runner_used"] == "ui"
    assert result["fallback_used"] is True
    assert result["api_result_summary"] == {
        "ok": True,
        "run_id": "api-1",
        "error_code": "",
        "mismatch_code": "missing_detail_rows",
    }
    assert len(ui.calls) == 1
    assert catalog.observations[-1]["runner_used"] == "ui"


@pytest.mark.asyncio
async def test_explicit_api_does_not_fallback_to_ui():
    api = FakeApiRunner(
        {
            "ok": True,
            "run_id": "api-1",
            "contract_validation": {"matched": False, "mismatch_code": "missing_detail_rows"},
        }
    )
    ui = FakeUiRunner({"ok": True, "run_id": "ui-1"})

    result = await ReportOrchestrator(
        catalog=FakeCatalog(),
        api_runner=api,
        ui_runner=ui,
        settings=ReportEngineSettings(api_enabled=True, ui_enabled=True, ui_fallback_enabled=True),
    ).run_report(database="ERP_DEMO", report="R", variant="", runner="api", period=None, filters={}, params={})

    assert result["runner_used"] == "api"
    assert result["fallback_used"] is False
    assert ui.calls == []


@pytest.mark.asyncio
async def test_policy_can_prefer_ui_first():
    api = FakeApiRunner({"ok": True, "run_id": "api-1"})
    ui = FakeUiRunner({"ok": True, "run_id": "ui-1"})

    result = await ReportOrchestrator(
        catalog=FakeCatalog({"preferred_runner": "ui", "ui_enabled": True}),
        api_runner=api,
        ui_runner=ui,
        settings=ReportEngineSettings(api_enabled=True, ui_enabled=True, ui_fallback_enabled=True),
    ).run_report(database="ERP_DEMO", report="R", variant="", runner="auto", period=None, filters={}, params={})

    assert result["runner_used"] == "ui"
    assert api.calls == []
    assert len(ui.calls) == 1


@pytest.mark.asyncio
async def test_ui_disabled_keeps_api_result_even_when_api_has_gap():
    api = FakeApiRunner(
        {
            "ok": True,
            "run_id": "api-1",
            "contract_validation": {"matched": False, "mismatch_code": "missing_detail_rows"},
        }
    )

    result = await ReportOrchestrator(
        catalog=FakeCatalog(),
        api_runner=api,
        ui_runner=None,
        settings=ReportEngineSettings(api_enabled=True, ui_enabled=False, ui_fallback_enabled=False),
    ).run_report(database="ERP_DEMO", report="R", variant="", runner="auto", period=None, filters={}, params={})

    assert result["runner_used"] == "api"
    assert result["fallback_used"] is False
    assert result["ui_available"] is False
