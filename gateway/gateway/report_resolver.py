"""Report title resolver for accountant-facing names."""

from __future__ import annotations

from .report_catalog import ReportCatalog


class ReportResolver:
    """Thin resolver wrapper used by MCP handlers and tests."""

    def __init__(self, catalog: ReportCatalog):
        self.catalog = catalog

    def resolve(
        self,
        database: str,
        *,
        title: str | None = None,
        report: str | None = None,
        variant: str | None = None,
    ) -> dict:
        return self.catalog.resolve_report(
            database,
            title=title,
            report=report,
            variant=variant,
        )
