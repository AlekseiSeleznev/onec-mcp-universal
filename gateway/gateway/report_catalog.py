"""SQLite-backed catalog for user-facing 1C report discovery and runs."""

from __future__ import annotations

import difflib
import gzip
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .report_failure import effective_report_run_status


_PUNCT_RE = re.compile(r"[^0-9a-zа-яёA-ZА-ЯЁ]+", re.IGNORECASE)
_CAMEL_RE = re.compile(r"(?<=[0-9a-zа-яё])(?=[A-ZА-ЯЁ])")


def normalize_report_query(value: str) -> str:
    """Normalize accountant-facing report titles for stable lookup."""
    split = _CAMEL_RE.sub(" ", value or "")
    split = split.replace("ё", "е").replace("Ё", "Е").lower()
    split = _PUNCT_RE.sub(" ", split)
    return " ".join(split.split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class ReportCatalog:
    """Persistent multi-database report catalog."""

    def __init__(self, db_path: str | Path = "/data/report-catalog.sqlite", results_dir: str | Path = "/data/report-results"):
        self.db_path = Path(db_path)
        self.results_dir = Path(results_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS catalog_meta (
                    db_slug TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    config_fingerprint TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS reports (
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    report_synonym TEXT NOT NULL DEFAULT '',
                    source_path TEXT NOT NULL DEFAULT '',
                    report_fingerprint TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'unsupported',
                    status TEXT NOT NULL DEFAULT 'unsupported',
                    confidence REAL NOT NULL DEFAULT 0,
                    diagnostics_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (db_slug, report_name)
                );
                CREATE TABLE IF NOT EXISTS report_aliases (
                    db_slug TEXT NOT NULL,
                    alias_norm TEXT NOT NULL,
                    alias_display TEXT NOT NULL,
                    alias_source TEXT NOT NULL DEFAULT '',
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL DEFAULT '',
                    template_name TEXT NOT NULL DEFAULT '',
                    strategy_hint TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    locale TEXT NOT NULL DEFAULT 'ru'
                );
                CREATE INDEX IF NOT EXISTS idx_report_aliases_lookup
                    ON report_aliases(db_slug, alias_norm);
                CREATE TABLE IF NOT EXISTS report_variants (
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL,
                    presentation TEXT NOT NULL DEFAULT '',
                    template_name TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (db_slug, report_name, variant_key)
                );
                CREATE TABLE IF NOT EXISTS report_params (
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    presentation TEXT NOT NULL DEFAULT '',
                    type_name TEXT NOT NULL DEFAULT '',
                    required INTEGER NOT NULL DEFAULT 0,
                    default_json TEXT NOT NULL DEFAULT 'null',
                    source TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (db_slug, report_name, variant_key, name)
                );
                CREATE TABLE IF NOT EXISTS report_strategies (
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL DEFAULT '',
                    strategy TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    confidence REAL NOT NULL DEFAULT 0,
                    entrypoint TEXT NOT NULL DEFAULT '',
                    output_type TEXT NOT NULL DEFAULT 'rows',
                    requires_runtime_probe INTEGER NOT NULL DEFAULT 0,
                    blocked_reason TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (db_slug, report_name, variant_key, strategy, entrypoint)
                );
                CREATE INDEX IF NOT EXISTS idx_report_strategies_lookup
                    ON report_strategies(db_slug, report_name, variant_key, priority);
                CREATE TABLE IF NOT EXISTS report_docs (
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    query TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    parsed_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    error TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (db_slug, report_name, variant_key, source)
                );
                CREATE INDEX IF NOT EXISTS idx_report_docs_lookup
                    ON report_docs(db_slug, report_name, variant_key);
                CREATE TABLE IF NOT EXISTS report_runs (
                    run_id TEXT PRIMARY KEY,
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    strategy TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'running',
                    params_hash TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT NOT NULL DEFAULT '',
                    result_ref TEXT NOT NULL DEFAULT '',
                    diagnostics_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_report_runs_db_status
                    ON report_runs(db_slug, status);
                CREATE TABLE IF NOT EXISTS report_output_contracts (
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL DEFAULT '',
                    contract_source TEXT NOT NULL,
                    contract_hash TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    contract_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (db_slug, report_name, variant_key, contract_source)
                );
                CREATE INDEX IF NOT EXISTS idx_report_output_contracts_lookup
                    ON report_output_contracts(db_slug, report_name, variant_key, contract_source);
                CREATE TABLE IF NOT EXISTS report_validation_campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    db_slug TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'contracts',
                    status TEXT NOT NULL DEFAULT 'running',
                    stop_on_mismatch INTEGER NOT NULL DEFAULT 1,
                    fixture_pack_json TEXT NOT NULL DEFAULT '{}',
                    order_json TEXT NOT NULL DEFAULT '[]',
                    counts_json TEXT NOT NULL DEFAULT '{}',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT NOT NULL DEFAULT '',
                    stop_reason TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS report_validation_items (
                    campaign_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL DEFAULT 0,
                    db_slug TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    variant_key TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    terminal_state TEXT NOT NULL DEFAULT '',
                    strategy TEXT NOT NULL DEFAULT '',
                    run_id TEXT NOT NULL DEFAULT '',
                    contract_source TEXT NOT NULL DEFAULT '',
                    contract_hash TEXT NOT NULL DEFAULT '',
                    observed_json TEXT NOT NULL DEFAULT '{}',
                    mismatch_code TEXT NOT NULL DEFAULT '',
                    root_cause_class TEXT NOT NULL DEFAULT '',
                    diagnostics_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (campaign_id, report_name, variant_key)
                );
                CREATE INDEX IF NOT EXISTS idx_report_validation_items_lookup
                    ON report_validation_items(db_slug, report_name, variant_key, updated_at);
                """
            )

    def replace_analysis(self, database: str, project_path: str, payload: dict) -> dict:
        reports = list(payload.get("reports") or [])
        fingerprint = hashlib.sha256(_json_dumps(reports).encode("utf-8")).hexdigest()
        with self._connect() as conn:
            for table in (
                "report_aliases",
                "report_variants",
                "report_params",
                "report_strategies",
                "reports",
            ):
                conn.execute(f"DELETE FROM {table} WHERE db_slug = ?", (database,))
            conn.execute(
                "DELETE FROM report_output_contracts WHERE db_slug = ? AND contract_source = 'declared'",
                (database,),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO catalog_meta
                    (db_slug, project_path, config_fingerprint, analyzer_version)
                VALUES (?, ?, ?, ?)
                """,
                (database, str(project_path), fingerprint, "1"),
            )
            for report in reports:
                self._insert_report(conn, database, report)
        return {"ok": True, "database": database, "reports": len(reports), "fingerprint": fingerprint}

    def upsert_report_analysis(self, database: str, project_path: str, report: dict) -> dict:
        name = str(report.get("name") or "").strip()
        if not name:
            return {"ok": False, "error_code": "report_name_required"}
        fingerprint = hashlib.sha256(_json_dumps(report).encode("utf-8")).hexdigest()
        with self._connect() as conn:
            for table in (
                "report_aliases",
                "report_variants",
                "report_params",
                "report_strategies",
                "reports",
            ):
                conn.execute(f"DELETE FROM {table} WHERE db_slug = ? AND report_name = ?", (database, name))
            conn.execute(
                "DELETE FROM report_output_contracts WHERE db_slug = ? AND report_name = ? AND contract_source = 'declared'",
                (database, name),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO catalog_meta
                    (db_slug, project_path, config_fingerprint, analyzer_version)
                VALUES (?, ?, ?, ?)
                """,
                (database, str(project_path), fingerprint, "1"),
            )
            self._insert_report(conn, database, report)
        return {"ok": True, "database": database, "report": name, "fingerprint": fingerprint}

    def list_reports(self, database: str, query: str = "", limit: int = 50) -> list[dict]:
        if query:
            return self.find_reports(database, query, limit)
        rows = self._query_reports(database)
        return rows[: max(0, limit)]

    def find_reports(self, database: str, query: str, limit: int = 10) -> list[dict]:
        norm = normalize_report_query(query)
        candidates = self._query_reports(database) + self._query_doc_reports(database)
        scored = []
        for row in candidates:
            alias_norm = row["alias_norm"]
            doc_norm = str(row.get("doc_norm") or "")
            if not norm:
                score = float(row["confidence"])
            elif alias_norm == norm or normalize_report_query(row["report"]) == norm:
                score = 1.0
            elif norm in alias_norm or alias_norm in norm:
                score = 0.85
            elif doc_norm and norm in doc_norm:
                score = 0.80
            else:
                score = difflib.SequenceMatcher(None, norm, alias_norm).ratio()
            if not norm or score >= 0.35:
                public_row = {key: value for key, value in row.items() if key != "doc_norm"}
                scored.append({**public_row, "score": round(score, 4)})
        scored.sort(key=lambda item: (-item["score"], -float(item["confidence"]), item["title"]))
        return scored[: max(0, limit)]

    def describe_report(
        self,
        database: str,
        *,
        title: str | None = None,
        report: str | None = None,
        variant: str | None = None,
    ) -> dict:
        resolved = self.resolve_report(database, title=title, report=report, variant=variant)
        if not resolved["ok"]:
            return resolved
        report_name = resolved["report"]["report"]
        variant_key = resolved["report"].get("variant", "")
        output_contracts = self._fetch_output_contracts(database, report_name, variant_key)
        return {
            **resolved,
            "variants": self._fetch_variants(database, report_name),
            "params": self._fetch_params(database, report_name, variant_key),
            "strategies": self._fetch_strategies(database, report_name, variant_key),
            "output_contracts": output_contracts,
            "output_contract": (
                {**output_contracts[0]["contract"], "source": output_contracts[0]["source"], "hash": output_contracts[0]["hash"]}
                if output_contracts else {}
            ),
            "last_contract_validation": self.get_latest_contract_validation(database, report_name, variant_key),
            "docs": self.get_report_docs(database, report_name, variant_key),
        }

    def resolve_report(
        self,
        database: str,
        *,
        title: str | None = None,
        report: str | None = None,
        variant: str | None = None,
    ) -> dict:
        if report:
            row = self._fetch_report_alias(database, report, variant or "")
            if row:
                return {"ok": True, "report": row}
            return {"ok": False, "error_code": "report_not_found", "candidates": self.find_reports(database, report, 5)}

        candidates = self.find_reports(database, title or "", limit=10)
        if not candidates:
            return {"ok": False, "error_code": "report_not_found", "candidates": []}
        top_score = candidates[0]["score"]
        exact_ties = [row for row in candidates if row["score"] == top_score and top_score >= 0.98]
        exact_reports = {row["report"] for row in exact_ties}
        exact_variant_keys = {(row["report"], row.get("variant", "")) for row in exact_ties if row.get("variant", "")}
        if len(exact_reports) > 1 or len(exact_variant_keys) > 1:
            return {"ok": False, "error_code": "ambiguous_report", "candidates": exact_ties}
        if top_score < 0.65:
            return {"ok": False, "error_code": "report_not_found", "candidates": candidates[:5]}
        return {"ok": True, "report": candidates[0]}

    def create_run(
        self,
        *,
        database: str,
        report_name: str,
        variant_key: str,
        title: str,
        strategy: str,
        params: dict,
    ) -> str:
        run_id = uuid.uuid4().hex
        params_hash = hashlib.sha256(_json_dumps(params).encode("utf-8")).hexdigest()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO report_runs
                    (run_id, db_slug, report_name, variant_key, title, strategy, params_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, database, report_name, variant_key or "", title or "", strategy or "", params_hash),
            )
        return run_id

    def finish_run(
        self,
        database: str,
        run_id: str,
        *,
        status: str,
        result: dict | None = None,
        diagnostics: dict | None = None,
        error: str = "",
    ) -> None:
        result_ref = ""
        if result is not None:
            result_path = self.results_dir / database / f"{run_id}.json.gz"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(result_path, "wt", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False)
            result_ref = str(result_path)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE report_runs
                SET status = ?, finished_at = CURRENT_TIMESTAMP, result_ref = ?,
                    diagnostics_json = ?, error = ?
                WHERE db_slug = ? AND run_id = ?
                """,
                (status, result_ref, _json_dumps(diagnostics or {}), error, database, run_id),
            )

    def get_report_result(self, database: str, run_id: str, offset: int = 0, limit: int = 1000) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_runs WHERE db_slug = ? AND run_id = ?",
                (database, run_id),
            ).fetchone()
        if row is None:
            return {"ok": False, "error_code": "report_result_not_found"}
        result: dict[str, Any] = {}
        if row["result_ref"]:
            with gzip.open(row["result_ref"], "rt", encoding="utf-8") as fh:
                result = json.load(fh)
        rows = list(result.get("rows") or [])
        start = max(0, int(offset or 0))
        stop = start + max(0, int(limit or 0))
        return {
            "ok": row["status"] == "done",
            "run_id": run_id,
            "status": row["status"],
            "columns": result.get("columns", []),
            "rows": rows[start:stop],
            "total_rows": len(rows),
            "totals": result.get("totals", {}),
            "metadata": result.get("metadata", {}),
            "diagnostics_json": row["diagnostics_json"],
            "error": row["error"],
        }

    def upsert_report_doc(
        self,
        *,
        database: str,
        report_name: str,
        variant_key: str = "",
        source: str,
        query: str,
        content: str,
        parsed: dict | None = None,
        error: str = "",
    ) -> None:
        parsed = parsed or {}
        confidence = float(parsed.get("confidence") or 0.70)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO report_docs
                    (db_slug, report_name, variant_key, source, query, content,
                     parsed_json, confidence, fetched_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    database,
                    report_name,
                    variant_key or "",
                    source,
                    query,
                    content,
                    _json_dumps(parsed),
                    confidence,
                    error,
                ),
            )

    def get_report_docs(self, database: str, report_name: str, variant_key: str = "") -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM report_docs
                WHERE db_slug = ? AND report_name = ? AND (variant_key = ? OR variant_key = '')
                ORDER BY confidence DESC, fetched_at DESC
                """,
                (database, report_name, variant_key or ""),
            ).fetchall()
        return [
            {
                "source": row["source"],
                "query": row["query"],
                "content": row["content"],
                "title": str(_json_loads(row["parsed_json"], {}).get("title") or ""),
                "aliases": list(_json_loads(row["parsed_json"], {}).get("aliases") or []),
                "summary": str(_json_loads(row["parsed_json"], {}).get("summary") or ""),
                "source_urls": list(_json_loads(row["parsed_json"], {}).get("source_urls") or []),
                "confidence": row["confidence"],
                "fetched_at": row["fetched_at"],
                "error": row["error"],
            }
            for row in rows
        ]

    def summarize_databases(self, databases: list[str] | None = None, top_n: int = 3) -> list[dict]:
        with self._connect() as conn:
            meta_rows = conn.execute(
                "SELECT db_slug, analyzed_at FROM catalog_meta ORDER BY db_slug"
            ).fetchall()
            meta_by_db = {row["db_slug"]: row["analyzed_at"] for row in meta_rows}
            report_names_by_db: dict[str, set[str]] = {}
            for row in conn.execute(
                "SELECT db_slug, report_name FROM reports ORDER BY db_slug, report_name"
            ).fetchall():
                report_names_by_db.setdefault(row["db_slug"], set()).add(row["report_name"])

            report_counts = {
                row["db_slug"]: row["count"]
                for row in conn.execute(
                    "SELECT db_slug, COUNT(*) AS count FROM reports GROUP BY db_slug"
                ).fetchall()
            }
            variant_counts = {
                row["db_slug"]: row["count"]
                for row in conn.execute(
                    "SELECT db_slug, COUNT(*) AS count FROM report_variants GROUP BY db_slug"
                ).fetchall()
            }
            run_rows = conn.execute(
                """
                SELECT rowid AS _rowid, db_slug, report_name, variant_key, status,
                       diagnostics_json, error, result_ref, started_at, finished_at
                FROM report_runs
                ORDER BY COALESCE(NULLIF(finished_at, ''), started_at) DESC, rowid DESC
                """
            ).fetchall()

        database_names = list(databases or [])
        if not database_names:
            seen = set(meta_by_db) | set(report_counts) | set(variant_counts) | {row["db_slug"] for row in run_rows}
            database_names = sorted(seen)
        else:
            database_names = sorted(dict.fromkeys(database_names))

        run_groups: dict[str, list[sqlite3.Row]] = {}
        for row in run_rows:
            run_groups.setdefault(row["db_slug"], []).append(row)

        summary = []
        for database in database_names:
            rows = run_groups.get(database, [])
            catalog_report_names = report_names_by_db.get(database, set())
            latest_rows: list[sqlite3.Row] = []
            seen_reports: set[str] = set()
            for row in rows:
                report_name = str(row["report_name"] or "").strip()
                if not report_name:
                    continue
                if catalog_report_names and report_name not in catalog_report_names:
                    continue
                if report_name in seen_reports:
                    continue
                seen_reports.add(report_name)
                latest_rows.append(row)

            status_counts = {"done": 0, "needs_input": 0, "unsupported": 0, "error": 0}
            issue_counts: dict[str, int] = {}
            results_count = 0
            for row in latest_rows:
                diagnostics = _json_loads(row["diagnostics_json"], {})
                status, effective_diagnostics = effective_report_run_status(
                    str(row["status"] or ""),
                    diagnostics,
                    str(row["error"] or ""),
                )
                if status in status_counts:
                    status_counts[status] += 1
                else:
                    status_counts["error"] += 1
                if row["result_ref"]:
                    result_path = Path(str(row["result_ref"]))
                    if not result_path.is_absolute():
                        result_path = self.results_dir / str(row["result_ref"])
                    if result_path.exists():
                        results_count += 1
                issue_label = ""
                if status == "unsupported":
                    issue_label = str(effective_diagnostics.get("unsupported_reason") or row["error"] or "").strip()
                elif status in {"needs_input", "error"}:
                    issue_label = str(row["error"] or "").strip()
                if issue_label:
                    issue_counts[issue_label] = issue_counts.get(issue_label, 0) + 1
            top_issues = [
                {"label": label, "count": count}
                for label, count in sorted(issue_counts.items(), key=lambda item: (-item[1], item[0]))[: max(1, int(top_n or 0))]
            ]
            summary.append(
                {
                    "database": database,
                    "catalog_ready": database in meta_by_db or report_counts.get(database, 0) > 0,
                    "analyzed_at": str(meta_by_db.get(database) or ""),
                    "reports_count": int(report_counts.get(database, 0) or 0),
                    "variants_count": int(variant_counts.get(database, 0) or 0),
                    "runs_count": len(latest_rows),
                    "history_runs_count": len(rows),
                    "artifacts_count": results_count,
                    "status_counts": status_counts,
                    "top_issues": top_issues,
                    "summary_mode": "latest_report_run",
                }
            )
        return summary

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _insert_report(self, conn: sqlite3.Connection, database: str, report: dict) -> None:
        name = str(report.get("name") or "").strip()
        if not name:
            return
        fingerprint = hashlib.sha256(_json_dumps(report).encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT INTO reports
                (db_slug, report_name, report_synonym, source_path, report_fingerprint,
                 kind, status, confidence, diagnostics_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                database,
                name,
                str(report.get("synonym") or ""),
                str(report.get("source_path") or ""),
                fingerprint,
                str(report.get("kind") or "unsupported"),
                str(report.get("status") or "unsupported"),
                float(report.get("confidence") or 0),
                _json_dumps(report.get("diagnostics") or {}),
            ),
        )
        aliases = list(report.get("aliases") or [])
        if report.get("synonym"):
            aliases.append({"alias": report["synonym"], "source": "report", "confidence": 0.70})
        aliases.append({"alias": name, "source": "technical", "confidence": 0.6})
        for alias in aliases:
            display = str(alias.get("alias") or "").strip()
            if not display:
                continue
            conn.execute(
                """
                INSERT INTO report_aliases
                    (db_slug, alias_norm, alias_display, alias_source, report_name,
                     variant_key, template_name, strategy_hint, confidence, locale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    database,
                    normalize_report_query(display),
                    display,
                    str(alias.get("source") or ""),
                    name,
                    str(alias.get("variant") or ""),
                    str(alias.get("template") or ""),
                    str(alias.get("strategy_hint") or ""),
                    float(alias.get("confidence") or report.get("confidence") or 0),
                    str(alias.get("locale") or "ru"),
                ),
            )
        for variant in report.get("variants") or []:
            key = str(variant.get("key") or "").strip()
            if key:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO report_variants
                        (db_slug, report_name, variant_key, presentation, template_name, details_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        database,
                        name,
                        key,
                        str(variant.get("presentation") or ""),
                        str(variant.get("template") or ""),
                        _json_dumps(variant.get("details") or {}),
                    ),
                )
        for param in report.get("params") or []:
            param_name = str(param.get("name") or "").strip()
            if param_name:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO report_params
                        (db_slug, report_name, variant_key, name, presentation, type_name,
                         required, default_json, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        database,
                        name,
                        str(param.get("variant") or ""),
                        param_name,
                        str(param.get("presentation") or param_name),
                        str(param.get("type_name") or ""),
                        1 if param.get("required") else 0,
                        _json_dumps(param.get("default")),
                        str(param.get("source") or ""),
                    ),
                )
        for strategy in report.get("strategies") or []:
            strategy_name = str(strategy.get("strategy") or "").strip()
            if strategy_name:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO report_strategies
                        (db_slug, report_name, variant_key, strategy, priority, confidence,
                         entrypoint, output_type, requires_runtime_probe, blocked_reason, details_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        database,
                        name,
                        str(strategy.get("variant") or ""),
                        strategy_name,
                        int(strategy.get("priority") or 100),
                        float(strategy.get("confidence") or 0),
                        str(strategy.get("entrypoint") or ""),
                        str(strategy.get("output_type") or "rows"),
                        1 if strategy.get("requires_runtime_probe") else 0,
                        str(strategy.get("blocked_reason") or ""),
                        _json_dumps(strategy.get("details") or {}),
                    ),
                )
        for output_contract in report.get("output_contracts") or []:
            source = str(output_contract.get("source") or "").strip()
            contract = output_contract.get("contract") if isinstance(output_contract.get("contract"), dict) else {}
            if source and contract:
                self._upsert_output_contract_conn(
                    conn,
                    database,
                    name,
                    str(output_contract.get("variant") or ""),
                    source,
                    contract,
                )

    def upsert_output_contract(
        self,
        database: str,
        report_name: str,
        variant_key: str,
        contract_source: str,
        contract: dict,
    ) -> None:
        with self._connect() as conn:
            self._upsert_output_contract_conn(conn, database, report_name, variant_key, contract_source, contract)

    def create_validation_campaign(
        self,
        database: str,
        *,
        mode: str,
        fixture_pack: dict | None = None,
        order: list[dict] | None = None,
        stop_on_mismatch: bool = True,
    ) -> str:
        campaign_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO report_validation_campaigns
                    (campaign_id, db_slug, mode, stop_on_mismatch, fixture_pack_json, order_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    database,
                    mode,
                    1 if stop_on_mismatch else 0,
                    _json_dumps(fixture_pack or {}),
                    _json_dumps(order or []),
                ),
            )
        return campaign_id

    def upsert_validation_item(
        self,
        campaign_id: str,
        *,
        ordinal: int,
        database: str,
        report_name: str,
        variant_key: str,
        title: str,
        status: str,
        terminal_state: str,
        strategy: str = "",
        run_id: str = "",
        contract_source: str = "",
        contract_hash: str = "",
        observed: dict | None = None,
        mismatch_code: str = "",
        root_cause_class: str = "",
        diagnostics: dict | None = None,
        error: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO report_validation_items
                    (campaign_id, ordinal, db_slug, report_name, variant_key, title, status,
                     terminal_state, strategy, run_id, contract_source, contract_hash,
                     observed_json, mismatch_code, root_cause_class, diagnostics_json, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    campaign_id,
                    ordinal,
                    database,
                    report_name,
                    variant_key or "",
                    title or report_name,
                    status,
                    terminal_state,
                    strategy,
                    run_id,
                    contract_source,
                    contract_hash,
                    _json_dumps(observed or {}),
                    mismatch_code,
                    root_cause_class,
                    _json_dumps(diagnostics or {}),
                    error,
                ),
            )

    def mark_validation_campaign_running(self, campaign_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE report_validation_campaigns
                SET status = 'running', finished_at = '', stop_reason = ?
                WHERE campaign_id = ?
                """,
                ("", campaign_id),
            )

    def update_validation_campaign_fixture_pack(self, campaign_id: str, fixture_pack: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE report_validation_campaigns
                SET fixture_pack_json = ?
                WHERE campaign_id = ?
                """,
                (_json_dumps(fixture_pack or {}), campaign_id),
            )

    def update_validation_campaign_order(self, campaign_id: str, order: list[dict]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE report_validation_campaigns
                SET order_json = ?
                WHERE campaign_id = ?
                """,
                (_json_dumps(order or []), campaign_id),
            )

    def summarize_validation_campaign(self, campaign_id: str) -> dict:
        counts = {
            "matched": 0,
            "deferred_context": 0,
            "deferred_unsupported": 0,
            "deferred_engine_gap": 0,
            "deferred_analyzer_gap": 0,
            "error": 0,
        }
        with self._connect() as conn:
            campaign = conn.execute(
                "SELECT order_json FROM report_validation_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT ordinal, report_name, variant_key, title, status, terminal_state, strategy,
                       run_id, contract_source, contract_hash, observed_json, mismatch_code,
                       root_cause_class, diagnostics_json, error
                FROM report_validation_items
                WHERE campaign_id = ?
                ORDER BY ordinal, report_name, variant_key
                """,
                (campaign_id,),
            ).fetchall()
        items = []
        stopper_item: dict | None = None
        for row in rows:
            terminal_state = str(row["terminal_state"] or row["status"] or "error")
            counts[terminal_state if terminal_state in counts else "error"] += 1
            item = {
                "ordinal": row["ordinal"],
                "report": row["report_name"],
                "variant": row["variant_key"],
                "title": row["title"],
                "status": row["status"],
                "terminal_state": terminal_state,
                "strategy": row["strategy"],
                "run_id": row["run_id"],
                "contract_source": row["contract_source"],
                "contract_hash": row["contract_hash"],
                "observed": _json_loads(row["observed_json"], {}),
                "mismatch_code": row["mismatch_code"],
                "root_cause_class": row["root_cause_class"],
                "diagnostics": _json_loads(row["diagnostics_json"], {}),
                "error": row["error"],
            }
            items.append(item)
            if stopper_item is None and terminal_state in {"deferred_engine_gap", "deferred_analyzer_gap", "error"}:
                stopper_item = item
        return {
            "counts": counts,
            "summary": {
                "processed": len(items),
                "total_targets": len(_json_loads(campaign["order_json"] if campaign else "[]", [])),
                "last_ordinal": items[-1]["ordinal"] if items else 0,
                "resume_from_ordinal": stopper_item["ordinal"] if stopper_item else ((items[-1]["ordinal"] + 1) if items else 1),
            },
            "stopper_item": stopper_item or {},
            "items": items,
        }

    def finish_validation_campaign(
        self,
        campaign_id: str,
        *,
        status: str,
        counts: dict,
        summary: dict | None = None,
        stop_reason: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE report_validation_campaigns
                SET status = ?, counts_json = ?, summary_json = ?, finished_at = CURRENT_TIMESTAMP, stop_reason = ?
                WHERE campaign_id = ?
                """,
                (status, _json_dumps(counts), _json_dumps(summary or {}), stop_reason, campaign_id),
            )

    def get_validation_campaign(self, campaign_id: str) -> dict:
        with self._connect() as conn:
            campaign = conn.execute(
                "SELECT * FROM report_validation_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        if campaign is None:
            return {"ok": False, "error_code": "campaign_not_found"}
        live_summary = self.summarize_validation_campaign(campaign_id)
        return {
            "ok": True,
            "campaign_id": campaign_id,
            "database": campaign["db_slug"],
            "mode": campaign["mode"],
            "status": campaign["status"],
            "stop_on_mismatch": bool(campaign["stop_on_mismatch"]),
            "fixture_pack": _json_loads(campaign["fixture_pack_json"], {}),
            "order": _json_loads(campaign["order_json"], []),
            "counts": live_summary.get("counts") or _json_loads(campaign["counts_json"], {}),
            "summary": live_summary.get("summary") or _json_loads(campaign["summary_json"], {}),
            "started_at": campaign["started_at"],
            "finished_at": campaign["finished_at"],
            "stop_reason": campaign["stop_reason"],
            "items": live_summary.get("items") or [],
        }

    def get_latest_contract_validation(self, database: str, report_name: str, variant_key: str = "") -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM report_validation_items
                WHERE db_slug = ? AND report_name = ? AND variant_key = ?
                ORDER BY updated_at DESC, ordinal DESC
                LIMIT 1
                """,
                (database, report_name, variant_key or ""),
            ).fetchone()
        if row is None:
            return {}
        return {
            "campaign_id": row["campaign_id"],
            "status": row["status"],
            "terminal_state": row["terminal_state"],
            "strategy": row["strategy"],
            "run_id": row["run_id"],
            "contract_source": row["contract_source"],
            "mismatch_code": row["mismatch_code"],
            "root_cause_class": row["root_cause_class"],
            "observed": _json_loads(row["observed_json"], {}),
            "diagnostics": _json_loads(row["diagnostics_json"], {}),
            "error": row["error"],
        }

    def _query_reports(self, database: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.report_name, r.report_synonym, r.kind, r.status, r.confidence AS report_confidence,
                       a.alias_norm, a.alias_display, a.alias_source, a.variant_key, a.confidence,
                       CASE
                           WHEN EXISTS (
                               SELECT 1
                               FROM report_strategies s
                               WHERE s.db_slug = a.db_slug
                                 AND s.report_name = a.report_name
                                 AND (s.variant_key = a.variant_key OR s.variant_key = '')
                           )
                           THEN 'supported'
                           ELSE 'unsupported'
                       END AS alias_status
                FROM report_aliases a
                JOIN reports r ON r.db_slug = a.db_slug AND r.report_name = a.report_name
                WHERE a.db_slug = ?
                ORDER BY r.report_name, a.confidence DESC
                """,
                (database,),
            ).fetchall()
        dedup: dict[tuple[str, str], dict] = {}
        for row in rows:
            key = (row["report_name"], row["variant_key"])
            current = dedup.get(key)
            item = {
                "title": row["alias_display"],
                "report": row["report_name"],
                "variant": row["variant_key"],
                "alias_source": row["alias_source"],
                "alias_norm": row["alias_norm"],
                "kind": row["kind"],
                "status": row["alias_status"],
                "confidence": row["confidence"],
            }
            if current is None or float(item["confidence"]) > float(current["confidence"]):
                dedup[key] = item
        return list(dedup.values())

    def _query_doc_reports(self, database: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*, r.kind, r.status AS report_status,
                       CASE
                           WHEN EXISTS (
                               SELECT 1
                               FROM report_strategies s
                               WHERE s.db_slug = d.db_slug
                                 AND s.report_name = d.report_name
                                 AND (s.variant_key = d.variant_key OR s.variant_key = '')
                           )
                           THEN 'supported'
                           ELSE 'unsupported'
                       END AS alias_status
                FROM report_docs d
                JOIN reports r ON r.db_slug = d.db_slug AND r.report_name = d.report_name
                WHERE d.db_slug = ? AND d.error = ''
                ORDER BY d.confidence DESC, d.fetched_at DESC
                """,
                (database,),
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            parsed = _json_loads(row["parsed_json"], {})
            aliases = self._doc_aliases(parsed, row["content"])
            for alias in aliases:
                result.append(
                    {
                        "title": alias,
                        "report": row["report_name"],
                        "variant": row["variant_key"],
                        "alias_source": f"doc:{row['source']}",
                        "alias_norm": normalize_report_query(alias),
                        "kind": row["kind"],
                        "status": row["alias_status"],
                        "confidence": row["confidence"],
                        "doc_norm": normalize_report_query(" ".join([row["content"], _json_dumps(parsed)])),
                    }
                )
        return result

    @staticmethod
    def _doc_aliases(parsed: dict, content: str) -> list[str]:
        result: list[str] = []
        title = str(parsed.get("title") or "").strip()
        if title:
            result.append(title)
        result.extend(str(alias).strip() for alias in parsed.get("aliases") or [] if str(alias).strip())
        normalized_title = normalize_report_query(" ".join(result))
        if "расчетный листок" in normalized_title:
            result.extend(["расчетка", "расчетка сотрудника", "листок по зарплате", "расчетный листок сотрудника"])
        if not result:
            summary = str(parsed.get("summary") or content or "").strip()
            if summary:
                result.append(summary[:120])
        deduped: list[str] = []
        seen = set()
        for alias in result:
            norm = normalize_report_query(alias)
            if norm and norm not in seen:
                deduped.append(alias)
                seen.add(norm)
        return deduped

    def _fetch_report_alias(self, database: str, report_name: str, variant: str = "") -> dict | None:
        rows = self._query_reports(database)
        for row in rows:
            if row["report"] == report_name and (not variant or row.get("variant") == variant):
                return row
        with self._connect() as conn:
            report = conn.execute(
                "SELECT * FROM reports WHERE db_slug = ? AND report_name = ?",
                (database, report_name),
            ).fetchone()
        if report is None:
            return None
        return {
            "title": report["report_synonym"] or report["report_name"],
            "report": report["report_name"],
            "variant": variant,
            "kind": report["kind"],
            "status": report["status"],
            "confidence": report["confidence"],
            "alias_source": "technical",
            "alias_norm": normalize_report_query(report["report_name"]),
        }

    def _fetch_variants(self, database: str, report_name: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM report_variants WHERE db_slug = ? AND report_name = ? ORDER BY variant_key",
                (database, report_name),
            ).fetchall()
        return [
            {
                "key": row["variant_key"],
                "presentation": row["presentation"],
                "template": row["template_name"],
                "details": _json_loads(row["details_json"], {}),
            }
            for row in rows
        ]

    def _fetch_params(self, database: str, report_name: str, variant: str = "") -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM report_params
                WHERE db_slug = ? AND report_name = ? AND (variant_key = ? OR variant_key = '')
                ORDER BY required DESC, name
                """,
                (database, report_name, variant or ""),
            ).fetchall()
        return [
            {
                "name": row["name"],
                "presentation": row["presentation"],
                "type_name": row["type_name"],
                "required": bool(row["required"]),
                "default": _json_loads(row["default_json"], None),
                "source": row["source"],
            }
            for row in rows
        ]

    def _fetch_strategies(self, database: str, report_name: str, variant: str = "") -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM report_strategies
                WHERE db_slug = ? AND report_name = ? AND (variant_key = ? OR variant_key = '')
                ORDER BY priority, confidence DESC
                """,
                (database, report_name, variant or ""),
            ).fetchall()
            if not rows and not variant:
                rows = conn.execute(
                    """
                    SELECT * FROM report_strategies
                    WHERE db_slug = ? AND report_name = ?
                    ORDER BY priority, confidence DESC
                    """,
                    (database, report_name),
                ).fetchall()
            preferred_strategy = self._preferred_strategy_conn(conn, database, report_name, variant or "")
        items = [
            {
                "strategy": row["strategy"],
                "priority": row["priority"],
                "confidence": row["confidence"],
                "entrypoint": row["entrypoint"],
                "output_type": row["output_type"],
                "requires_runtime_probe": bool(row["requires_runtime_probe"]),
                "blocked_reason": row["blocked_reason"],
                "details": _json_loads(row["details_json"], {}),
            }
            for row in rows
        ]
        if preferred_strategy:
            items.sort(key=lambda item: (item["strategy"] != preferred_strategy, item["priority"], -float(item["confidence"] or 0)))
        return items

    def _fetch_output_contracts(self, database: str, report_name: str, variant: str = "") -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM report_output_contracts
                WHERE db_slug = ? AND report_name = ? AND variant_key = ?
                ORDER BY CASE contract_source WHEN 'verified' THEN 0 ELSE 1 END, updated_at DESC
                """,
                (database, report_name, variant or ""),
            ).fetchall()
            if not rows and not variant:
                rows = conn.execute(
                    """
                    SELECT * FROM report_output_contracts
                    WHERE db_slug = ? AND report_name = ?
                    ORDER BY CASE contract_source WHEN 'verified' THEN 0 ELSE 1 END, updated_at DESC
                    """,
                    (database, report_name),
                ).fetchall()
        return [
            {
                "source": row["contract_source"],
                "hash": row["contract_hash"],
                "confidence": row["confidence"],
                "contract": _json_loads(row["contract_json"], {}),
            }
            for row in rows
        ]

    def _preferred_strategy_conn(self, conn: sqlite3.Connection, database: str, report_name: str, variant: str) -> str:
        row = conn.execute(
            """
            SELECT contract_json
            FROM report_output_contracts
            WHERE db_slug = ? AND report_name = ? AND variant_key = ?
            ORDER BY CASE contract_source WHEN 'verified' THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            (database, report_name, variant),
        ).fetchone()
        if row is None and not variant:
            row = conn.execute(
                """
                SELECT contract_json
                FROM report_output_contracts
                WHERE db_slug = ? AND report_name = ?
                ORDER BY CASE contract_source WHEN 'verified' THEN 0 ELSE 1 END, updated_at DESC
                LIMIT 1
                """,
                (database, report_name),
            ).fetchone()
        if row is None:
            return ""
        return str(_json_loads(row["contract_json"], {}).get("preferred_strategy") or "")

    def _upsert_output_contract_conn(
        self,
        conn: sqlite3.Connection,
        database: str,
        report_name: str,
        variant_key: str,
        contract_source: str,
        contract: dict,
    ) -> None:
        payload = dict(contract or {})
        payload.setdefault("source", contract_source)
        contract_hash = hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT OR REPLACE INTO report_output_contracts
                (db_slug, report_name, variant_key, contract_source, contract_hash, confidence, contract_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                database,
                report_name,
                variant_key or "",
                contract_source,
                contract_hash,
                float(payload.get("confidence_score") or 0),
                _json_dumps(payload),
            ),
        )
