"""Runner selection for 1C reports across API and UI execution paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


_FALLBACK_ERROR_CODES = {
    "unsupported_runtime",
    "report_timeout",
    "report_strategy_failed",
    "ui_runner_unavailable",
}
_FALLBACK_MISMATCH_CODES = {
    "header_only",
    "missing_detail_rows",
    "missing_expected_columns",
    "wrong_variant_shape",
    "artifact_instead_of_rows",
    "semantic_mismatch",
}


class ReportRunPath(Protocol):
    async def run_report(self, **kwargs) -> dict: ...


@dataclass(frozen=True)
class ReportEngineSettings:
    api_enabled: bool = True
    ui_enabled: bool = False
    ui_fallback_enabled: bool = False
    ui_export_format: str = "xlsx"
    keep_ui_error_artifacts: bool = False


class ReportOrchestrator:
    """Select API/UI report runners and persist lightweight observations."""

    def __init__(
        self,
        *,
        catalog: Any,
        api_runner: ReportRunPath | None,
        ui_runner: ReportRunPath | None,
        settings: ReportEngineSettings,
    ):
        self.catalog = catalog
        self.api_runner = api_runner
        self.ui_runner = ui_runner
        self.settings = settings

    async def run_report(self, *, runner: str = "auto", **kwargs) -> dict:
        requested = (runner or "auto").lower()
        if requested not in {"auto", "api", "ui"}:
            return {"ok": False, "error_code": "invalid_runner", "error": "runner must be api, ui, or auto"}
        report_name = str(kwargs.get("report") or "")
        variant_key = str(kwargs.get("variant") or "")
        policy = self._policy(str(kwargs.get("database") or ""), report_name, variant_key)

        if requested == "api":
            return await self._run_api(kwargs, fallback_used=False)
        if requested == "ui":
            return await self._run_ui(kwargs, fallback_used=False, api_result=None)

        first = self._first_runner(policy)
        if first == "ui":
            return await self._run_ui(kwargs, fallback_used=False, api_result=None)

        api_result = await self._run_api(kwargs, fallback_used=False)
        if not self._should_fallback_to_ui(api_result, policy):
            return api_result
        ui_result = await self._run_ui(kwargs, fallback_used=True, api_result=api_result)
        if ui_result.get("ok"):
            return ui_result
        api_result["ui_fallback_result"] = _result_summary(ui_result)
        return api_result

    def _first_runner(self, policy: dict) -> str:
        preferred = str(policy.get("preferred_runner") or "").lower()
        if preferred == "ui" and self._ui_allowed(policy):
            return "ui"
        if preferred == "api" and self._api_allowed(policy):
            return "api"
        if self._api_allowed(policy):
            return "api"
        if self._ui_allowed(policy):
            return "ui"
        return "api"

    def _should_fallback_to_ui(self, result: dict, policy: dict) -> bool:
        if not self.settings.ui_fallback_enabled or not self._ui_allowed(policy):
            return False
        if not result.get("ok"):
            return str(result.get("error_code") or "") in _FALLBACK_ERROR_CODES
        comparison = result.get("contract_validation") if isinstance(result.get("contract_validation"), dict) else {}
        if comparison.get("matched") or comparison.get("acceptable_with_verified"):
            return False
        return str(comparison.get("mismatch_code") or "") in _FALLBACK_MISMATCH_CODES

    async def _run_api(self, kwargs: dict, *, fallback_used: bool) -> dict:
        if not self._api_allowed({}):
            return {"ok": False, "error_code": "api_runner_disabled", "error": "API report runner is disabled", "runner_used": "api", "fallback_used": fallback_used}
        if self.api_runner is None:
            return {"ok": False, "error_code": "api_runner_unavailable", "error": "API report runner is unavailable", "runner_used": "api", "fallback_used": fallback_used}
        result = await self.api_runner.run_report(**kwargs)
        result.setdefault("runner_used", "api")
        result.setdefault("extractor_used", "api")
        result["fallback_used"] = fallback_used
        result.setdefault("ui_available", self.ui_runner is not None and self.settings.ui_enabled)
        self._record_observation(kwargs, result)
        return result

    async def _run_ui(self, kwargs: dict, *, fallback_used: bool, api_result: dict | None) -> dict:
        if not self.settings.ui_enabled and not fallback_used:
            return {"ok": False, "error_code": "ui_runner_disabled", "error": "UI report runner is disabled", "runner_used": "ui", "fallback_used": fallback_used}
        if self.ui_runner is None:
            return {"ok": False, "error_code": "ui_runner_unavailable", "error": "UI report runner is unavailable", "runner_used": "ui", "fallback_used": fallback_used}
        ui_kwargs = dict(kwargs)
        ui_kwargs.setdefault("export_format", self.settings.ui_export_format)
        result = await self.ui_runner.run_report(**ui_kwargs)
        result.setdefault("runner_used", "ui")
        result["fallback_used"] = fallback_used
        if api_result is not None:
            result["api_result_summary"] = _result_summary(api_result)
        self._record_observation(kwargs, result)
        return result

    def _api_allowed(self, policy: dict) -> bool:
        if policy.get("api_enabled") is False:
            return False
        return bool(self.settings.api_enabled)

    def _ui_allowed(self, policy: dict) -> bool:
        if policy.get("ui_enabled") is False:
            return False
        if policy.get("ui_enabled") is True:
            return bool(self.settings.ui_enabled and self.ui_runner is not None)
        return bool(self.settings.ui_enabled and self.ui_runner is not None)

    def _policy(self, database: str, report_name: str, variant_key: str) -> dict:
        if not report_name or not hasattr(self.catalog, "get_report_runner_policy"):
            return {}
        try:
            return dict(self.catalog.get_report_runner_policy(database, report_name, variant_key) or {})
        except Exception:
            return {}

    def _record_observation(self, kwargs: dict, result: dict) -> None:
        if not hasattr(self.catalog, "add_report_runner_observation"):
            return
        report_name = str(kwargs.get("report") or "")
        if not report_name:
            return
        comparison = result.get("contract_validation") if isinstance(result.get("contract_validation"), dict) else {}
        recommendation = ""
        if result.get("runner_used") == "ui" and result.get("ok"):
            recommendation = "prefer_ui" if result.get("fallback_used") else "ui_ok"
        elif result.get("runner_used") == "api" and result.get("ok") and comparison.get("matched", True):
            recommendation = "prefer_api"
        try:
            self.catalog.add_report_runner_observation(
                database=str(kwargs.get("database") or ""),
                report_name=report_name,
                variant_key=str(kwargs.get("variant") or ""),
                runner_used=str(result.get("runner_used") or ""),
                extractor_used=str(result.get("extractor_used") or ""),
                run_id=str(result.get("run_id") or ""),
                artifact_hash=str(result.get("artifact_hash") or ""),
                observed_signature=result.get("observed_signature") if isinstance(result.get("observed_signature"), dict) else {},
                recommendation=recommendation,
                diagnostics={
                    "ok": bool(result.get("ok")),
                    "error_code": str(result.get("error_code") or ""),
                    "mismatch_code": str(comparison.get("mismatch_code") or ""),
                    "fallback_used": bool(result.get("fallback_used")),
                },
            )
        except Exception:
            return


def _result_summary(result: dict) -> dict:
    comparison = result.get("contract_validation") if isinstance(result.get("contract_validation"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "run_id": str(result.get("run_id") or ""),
        "error_code": str(result.get("error_code") or ""),
        "mismatch_code": str(comparison.get("mismatch_code") or ""),
    }
