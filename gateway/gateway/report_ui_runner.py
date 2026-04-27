"""UI-based execution path for 1C reports through the web client."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from typing import Protocol

import httpx

from .report_catalog import ReportCatalog
from .report_contracts import build_verified_output_contract, compare_output_contract
from .report_result_extractor import ReportResultExtractor


class ReportUiClient(Protocol):
    async def export_report(self, **kwargs) -> dict: ...


class WebTestReportClient:
    """Adapter for skills/web-test/scripts/run.mjs.

    The adapter is intentionally optional. When Node/web-test is not available,
    the UI runner reports a structured unavailability error and the API runner
    remains fully usable.
    """

    def __init__(
        self,
        *,
        run_mjs: str | Path = "skills/web-test/scripts/run.mjs",
        node_bin: str = "node",
        web_url_template: str = "http://localhost:9090/{database}/ru/",
        startup_timeout_seconds: float = 45,
    ):
        raw_run_mjs = Path(run_mjs)
        self.run_mjs = raw_run_mjs if raw_run_mjs.is_absolute() else (Path.cwd() / raw_run_mjs)
        self.node_bin = node_bin
        self.web_url_template = web_url_template
        self.startup_timeout_seconds = float(startup_timeout_seconds or 45)

    async def export_report(self, **kwargs) -> dict:
        if not self.run_mjs.exists():
            return {"ok": False, "error_code": "ui_runner_unavailable", "error": f"web-test runner not found: {self.run_mjs}"}
        database = str(kwargs.get("database") or "")
        await self._ensure_session(database)
        script = self._build_script(kwargs)
        proc = await asyncio.to_thread(
            subprocess.run,
            [self.node_bin, str(self.run_mjs), "exec", "-", "--no-record"],
            input=script,
            text=True,
            capture_output=True,
            cwd=str(self.run_mjs.parent),
            timeout=max(60, int(kwargs.get("timeout_seconds") or 60)),
        )
        if proc.returncode != 0:
            return {"ok": False, "error_code": "ui_runner_failed", "error": (proc.stderr or proc.stdout).strip()}
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "error_code": "ui_runner_failed", "error": proc.stdout.strip()}
        if not payload.get("ok"):
            return {"ok": False, "error_code": "ui_runner_failed", "error": payload.get("error") or payload.get("output") or "web-test failed", "diagnostics": payload}
        return _parse_web_test_export_payload(payload)

    async def _ensure_session(self, database: str) -> None:
        status = await asyncio.to_thread(
            subprocess.run,
            [self.node_bin, str(self.run_mjs), "status"],
            text=True,
            capture_output=True,
            cwd=str(self.run_mjs.parent),
            timeout=10,
        )
        try:
            payload = json.loads(status.stdout)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("ok") and (payload.get("connected") or payload.get("port")):
            return
        url = self.web_url_template.format(database=database)
        subprocess.Popen(
            [self.node_bin, str(self.run_mjs), "start", url],
            cwd=str(self.run_mjs.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = asyncio.get_running_loop().time() + self.startup_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(1)
            status = await asyncio.to_thread(
                subprocess.run,
                [self.node_bin, str(self.run_mjs), "status"],
                text=True,
                capture_output=True,
                cwd=str(self.run_mjs.parent),
                timeout=10,
            )
            try:
                payload = json.loads(status.stdout)
            except json.JSONDecodeError:
                payload = {}
            if payload.get("ok") and (payload.get("connected") or payload.get("port")):
                return
        raise TimeoutError(f"UI web-test session did not start for {database}")

    def _build_script(self, kwargs: dict) -> str:
        report = str(kwargs.get("report") or "")
        artifact_path = str(kwargs.get("artifact_path") or "")
        ui_strategy = kwargs.get("ui_strategy") if isinstance(kwargs.get("ui_strategy"), dict) else {}
        export_settings = ui_strategy.get("export") if isinstance(ui_strategy.get("export"), dict) else {}
        export_format = str(export_settings.get("format") or kwargs.get("export_format") or "xlsx")
        fields = _ui_fields(kwargs.get("period") or {}, kwargs.get("filters") or {}, kwargs.get("params") or {}, ui_strategy)
        return _build_web_test_export_script(report, artifact_path, export_format, fields, ui_strategy, return_artifact_base64=False)


class WebTestHttpReportClient(WebTestReportClient):
    """Use an already-running web-test HTTP session from the gateway container."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url.rstrip("/")

    async def export_report(self, **kwargs) -> dict:
        artifact_path = str(kwargs.get("artifact_path") or "")
        script = self._build_http_script(kwargs)
        async with httpx.AsyncClient(timeout=max(60, float(kwargs.get("timeout_seconds") or 60))) as client:
            response = await client.post(
                self.base_url + "/exec",
                content=script,
                headers={"Content-Type": "text/plain; charset=utf-8", "X-No-Record": "1"},
            )
            response.raise_for_status()
            payload = response.json()
        parsed = _parse_web_test_export_payload(payload)
        if not parsed.get("ok"):
            return parsed
        artifact_base64 = str(parsed.pop("artifact_base64", "") or "")
        if artifact_base64:
            target = Path(artifact_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(artifact_base64))
            parsed["artifact_path"] = str(target)
        return parsed

    def _build_http_script(self, kwargs: dict) -> str:
        report = str(kwargs.get("report") or "")
        artifact_path = "/tmp/onec-report-ui-export"
        ui_strategy = kwargs.get("ui_strategy") if isinstance(kwargs.get("ui_strategy"), dict) else {}
        export_settings = ui_strategy.get("export") if isinstance(ui_strategy.get("export"), dict) else {}
        export_format = str(export_settings.get("format") or kwargs.get("export_format") or "xlsx")
        fields = _ui_fields(kwargs.get("period") or {}, kwargs.get("filters") or {}, kwargs.get("params") or {}, ui_strategy)
        return _build_web_test_export_script(report, artifact_path + "." + export_format, export_format, fields, ui_strategy, return_artifact_base64=True)


def _build_web_test_export_script(
    report: str,
    artifact_path: str,
    export_format: str,
    fields: dict,
    ui_strategy: dict,
    *,
    return_artifact_base64: bool,
) -> str:
    return f"""
const artifactPath = {json.dumps(artifact_path, ensure_ascii=False)};
const uiStrategy = {json.dumps(ui_strategy, ensure_ascii=False)};
const returnArtifactBase64 = {json.dumps(bool(return_artifact_base64))};
const openStrategy = uiStrategy.open || {{}};
if (openStrategy.mode === 'section_command' && openStrategy.section && openStrategy.command) {{
  await navigateSection(openStrategy.section);
  await openCommand(openStrategy.command);
}} else {{
  await navigateLink(openStrategy.metadata_path || {json.dumps("Отчет." + report, ensure_ascii=False)});
}}
await wait(2);
const fields = {json.dumps(fields, ensure_ascii=False)};
if (Object.keys(fields).length) {{
  await fillFields(fields);
}}
const generateAction = uiStrategy.generate_action || {{}};
await clickElement(generateAction.text || 'Сформировать');
await wait(5);
if (typeof exportSpreadsheet !== 'function') {{
  throw new Error('exportSpreadsheet is not available in web-test browser layer');
}}
const exported = await exportSpreadsheet({json.dumps(export_format)}, artifactPath);
if (returnArtifactBase64 && exported.artifact_path) {{
  exported.artifact_base64 = readFileSync(exported.artifact_path).toString('base64');
  try {{ unlinkSync(exported.artifact_path); }} catch (e) {{}}
}}
console.log('REPORT_UI_EXPORT_JSON=' + JSON.stringify(exported));
"""


def _parse_web_test_export_payload(payload: dict) -> dict:
    if not payload.get("ok"):
        return {"ok": False, "error_code": "ui_runner_failed", "error": payload.get("error") or payload.get("output") or "web-test failed", "diagnostics": payload}
    marker = "REPORT_UI_EXPORT_JSON="
    for line in str(payload.get("output") or "").splitlines():
        if line.startswith(marker):
            exported = json.loads(line[len(marker):])
            return {"ok": True, **exported, "diagnostics": {"web_test": payload}}
    return {"ok": False, "error_code": "ui_export_failed", "error": "web-test did not report exported artifact", "diagnostics": payload}


class ReportUiRunner:
    """Run one report through UI export and persist the normalized result."""

    def __init__(
        self,
        *,
        catalog: ReportCatalog,
        client: ReportUiClient,
        extractor: ReportResultExtractor | None = None,
        artifacts_dir: str | Path = "/data/report-ui-artifacts/tmp",
    ):
        self.catalog = catalog
        self.client = client
        self.extractor = extractor or ReportResultExtractor()
        self.artifacts_dir = Path(artifacts_dir)

    async def run_report(
        self,
        *,
        database: str,
        title: str = "",
        report: str | None = None,
        variant: str | None = None,
        period: dict | None = None,
        filters: dict | None = None,
        params: dict | None = None,
        context: dict | None = None,
        output: str = "rows",
        strategy: str = "auto",
        wait: bool = True,
        max_rows: int = 1000,
        timeout_seconds: float = 60,
        export_format: str = "xlsx",
        **_: object,
    ) -> dict:
        described = self.catalog.describe_report(database, title=title, report=report, variant=variant)
        if not described.get("ok"):
            return described
        report_name = described["report"]["report"]
        variant_key = described["report"].get("variant", "")
        run_title = title or described["report"].get("title") or report_name
        ui_strategy = _resolved_ui_strategy(self.catalog, database, report_name, variant_key, export_format)
        run_id = self.catalog.create_run(
            database=database,
            report_name=report_name,
            variant_key=variant_key,
            title=run_title,
            strategy=f"ui_{export_format}_runner",
            params={
                "period": period,
                "filters": filters or {},
                "params": params or {},
                "context": context or {},
                "output": output,
                "wait": wait,
                "runner": "ui",
                "ui_strategy_hash": ui_strategy.get("hash", ""),
            },
        )
        run_dir = self.artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = run_dir / f"report.{export_format}"
        exported = await self.client.export_report(
            database=database,
            title=run_title,
            report=report_name,
            variant=variant_key,
            period=period or {},
            filters=filters or {},
            params=params or {},
            context=context or {},
            artifact_path=str(artifact_path),
            export_format=export_format,
            ui_strategy=ui_strategy.get("strategy") or {},
            timeout_seconds=timeout_seconds,
        )
        if not exported.get("ok"):
            self.catalog.finish_run(
                database,
                run_id,
                status="error",
                diagnostics={"runner": "ui", "export": exported},
                error=str(exported.get("error") or "UI export failed"),
            )
            return {**exported, "run_id": run_id, "runner_used": "ui", "fallback_used": False}
        try:
            extracted = self.extractor.extract(
                exported.get("artifact_path") or artifact_path,
                artifact_format=str(exported.get("artifact_format") or export_format),
                cleanup=True,
            )
        except ValueError as exc:
            self.catalog.finish_run(
                database,
                run_id,
                status="error",
                diagnostics={"runner": "ui", "export": exported, "error_code": "ui_parse_failed"},
                error=str(exc),
            )
            return {"ok": False, "error_code": "ui_parse_failed", "error": str(exc), "run_id": run_id, "runner_used": "ui", "fallback_used": False}
        observed_signature = extracted.get("observed_signature") or {}
        expected_contract = described.get("output_contract") or {}
        comparison = compare_output_contract(expected_contract, observed_signature) if expected_contract else {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0}
        diagnostics = {
            "runner": "ui",
            "ui_strategy": ui_strategy,
            "export": {k: v for k, v in exported.items() if k != "diagnostics"},
            "export_diagnostics": exported.get("diagnostics") or {},
            "observed_signature": observed_signature,
            "contract_validation": comparison,
        }
        if comparison.get("matched") or comparison.get("acceptable_with_verified"):
            verified_contract = build_verified_output_contract(observed_signature, strategy_name=f"ui_{export_format}_runner")
            self.catalog.upsert_output_contract(database, report_name, variant_key, "verified", verified_contract)
            if hasattr(self.catalog, "upsert_report_ui_strategy"):
                self.catalog.upsert_report_ui_strategy(
                    database,
                    report_name,
                    variant_key,
                    ui_strategy.get("strategy") or {},
                    source="verified",
                )
        self.catalog.finish_run(database, run_id, status="done", result=extracted, diagnostics=diagnostics)
        result = {
            "ok": True,
            "run_id": run_id,
            "runner_used": "ui",
            "fallback_used": False,
            "contract_validation": comparison,
            **extracted,
        }
        self.catalog.add_report_runner_observation(
            database=database,
            report_name=report_name,
            variant_key=variant_key,
            runner_used="ui",
            extractor_used=str(extracted.get("extractor_used") or ""),
            run_id=run_id,
            artifact_hash=str(extracted.get("artifact_hash") or ""),
            observed_signature=observed_signature,
            recommendation="ui_ok" if result.get("ok") else "",
            diagnostics={"contract_validation": comparison},
        )
        return result


def _ui_fields(period: dict, filters: dict, params: dict, ui_strategy: dict | None = None) -> dict:
    parameter_map = {}
    if isinstance(ui_strategy, dict) and isinstance(ui_strategy.get("parameter_map"), dict):
        parameter_map = dict(ui_strategy.get("parameter_map") or {})
    fields: dict[str, object] = {}
    start_value = _format_ui_date(period.get("start") or period.get("from"))
    end_value = _format_ui_date(period.get("end") or period.get("to"))
    if start_value:
        fields[str(parameter_map.get("start") or "Начало периода")] = start_value
    if end_value:
        fields[str(parameter_map.get("end") or "Конец периода")] = end_value
    if start_value and end_value and parameter_map.get("period"):
        fields[str(parameter_map["period"])] = f"{start_value} - {end_value}"
    fields.update({str(parameter_map.get(str(k)) or k): v for k, v in params.items() if v not in (None, "")})
    fields.update({str(parameter_map.get(str(k)) or k): v for k, v in filters.items() if v not in (None, "")})
    return fields


def _format_ui_date(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        year, month, day = text.split("-")
        if year.isdigit() and month.isdigit() and day.isdigit():
            return f"{day}.{month}.{year}"
    return text


def _resolved_ui_strategy(catalog: ReportCatalog, database: str, report_name: str, variant_key: str, export_format: str) -> dict:
    strategy = catalog.get_report_ui_strategy(database, report_name, variant_key) if hasattr(catalog, "get_report_ui_strategy") else {}
    if strategy:
        return strategy
    payload = {
        "open": {"mode": "metadata_link", "metadata_path": f"Отчет.{report_name}"},
        "parameter_map": {
            "start": "Начало периода",
            "end": "Конец периода",
            "Организация": "Организация",
        },
        "generate_action": {"type": "click_text", "text": "Сформировать"},
        "export": {"format": export_format or "xlsx", "action": "save_as"},
    }
    return {"source": "default", "hash": "", "strategy": payload}
