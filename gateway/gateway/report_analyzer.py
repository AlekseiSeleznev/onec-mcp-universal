"""Static analyzer for 1C report metadata exported to BSL/XML files."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .report_catalog import ReportCatalog, normalize_report_query
from .report_contracts import build_declared_output_contract


_VARIANT_CALL_RE = re.compile(r"ОписаниеВарианта\s*\((?P<args>[^\n;)]*)\)", re.IGNORECASE)
_EXPORT_RE = re.compile(r"\b(?:Функция|Процедура)\s+([A-Za-zА-Яа-яЁё0-9_]+)\([^)]*\)\s+Экспорт", re.IGNORECASE)
_EXPORTED_FUNCTION_RE = re.compile(
    r"\bФункция\s+(?P<name>[A-Za-zА-Яа-яЁё0-9_]+)\((?P<params>[^)]*)\)\s+Экспорт",
    re.IGNORECASE,
)
_SKD_VARIANT_RE = re.compile(r"<settingsVariant\b[^>]*>(?P<body>.*?)</settingsVariant>", re.IGNORECASE | re.DOTALL)
_SKD_NAME_RE = re.compile(r"<(?:\w+:)?name\b[^>]*>(?P<name>[^<]+)</(?:\w+:)?name>", re.IGNORECASE)
_XML_CONTENT_RE = re.compile(r"<(?:\w+:)?content\b[^>]*>(?P<value>[^<]{3,120})</(?:\w+:)?content>", re.IGNORECASE)
_TEMPLATE_TYPE_RE = re.compile(r"<(?:\w+:)?TemplateType\b[^>]*>(?P<value>[^<]+)</(?:\w+:)?TemplateType>", re.IGNORECASE)
_BSL_AMP_PARAM_RE = re.compile(r"&(?:amp;)?(?P<name>[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)", re.IGNORECASE)
_BSL_MODULE_CALL_RE = re.compile(r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*\.[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*\s*\(")
_BSL_TEMP_TABLE_RE = re.compile(r"(?:\bиз|\bjoin|\bсоединение|\bпоместить|from)\s+вт[а-яёa-z0-9_]*", re.IGNORECASE)
_VARIANT_BRANCH_RE = re.compile(
    r"(?:Если|ИначеЕсли)\s+ВариантОтчета\s*=\s*\"(?P<variant>[^\"]+)\"\s+Тогда(?P<body>.*?)(?=(?:ИначеЕсли\s+ВариантОтчета\s*=|Иначе\b|КонецЕсли))",
    re.IGNORECASE | re.DOTALL,
)
_GET_LAYOUT_RE = re.compile(r"ПолучитьМакет\s*\(\s*\"(?P<layout>[^\"]+)\"\s*\)", re.IGNORECASE)
_QUALIFIED_CALL_RE = re.compile(
    r"(?:[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*\.\s*)+(?P<name>[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\(",
    re.IGNORECASE,
)
_MODULE_MEMBER_RE = re.compile(r"\b(?:Функция|Процедура)\s+(?P<name>[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\(", re.IGNORECASE)
_SAFE_RAW_SKD_PARAMS = {
    "дата",
    "датаначала",
    "датаконца",
    "датаокончания",
    "конецпериода",
    "началопериода",
    "период",
}
_XML_ENTITY_NAMES = {"gt", "lt", "amp", "quot", "apos"}
_SERVICE_ALIASES = {
    "data composition schema",
    "datacompositionschema",
    "основная схема компоновки данных",
    "основнаясхемакомпоновкиданных",
}
_CONTRACT_LAYOUT_SIZE_LIMIT = 1_000_000


class ReportAnalyzer:
    """Build report catalog entries from exported 1C source tree."""

    def __init__(self, catalog: ReportCatalog, graph_hints: dict | None = None):
        self.catalog = catalog
        self.graph_hints = graph_hints or {}

    def analyze_database(self, database: str, project_path: str | Path) -> dict:
        root = Path(project_path)
        payload = {"reports": [self._analyze_report(path, root) for path in sorted((root / "Reports").glob("*")) if path.is_dir()]}
        return self.catalog.replace_analysis(database, str(root), payload)

    def _analyze_report(self, report_dir: Path, root: Path) -> dict:
        name = report_dir.name
        template_entries = self._template_alias_entries(report_dir)
        template_aliases = [entry["alias"] for entry in template_entries]
        has_skd_templates = any(self._is_skd_template_entry(entry) for entry in template_entries)
        manager_text = self._read_text(report_dir / "Ext" / "ManagerModule.bsl")
        object_text = self._read_text(report_dir / "Ext" / "ObjectModule.bsl")
        selection_infos = self._template_selection_infos(report_dir)
        variants = self._attach_variant_details(self._variants(manager_text, template_entries, report_dir), selection_infos)
        exported = self._exported_entrypoints(manager_text)
        exported_functions = self._exported_functions(manager_text)
        xml_text = self._classification_xml_text(report_dir)
        help_text = self._report_help_text(report_dir)
        kind = self._classify_parts(manager_text, object_text, xml_text, has_skd_templates, bool(exported))
        graph = self._graph_summary(name)
        template_params = self._template_params(report_dir)
        strategies = self._strategies(
            name,
            kind,
            variants,
            root,
            graph,
            report_dir,
            object_text,
            exported_functions,
            self._has_variant_setup(manager_text),
        )
        report_title = self._report_title(name, template_aliases, variants)
        output_contracts = self._output_contracts(
            name,
            report_title,
            kind,
            variants,
            strategies,
            self._contract_texts(report_dir),
            manager_text,
            object_text,
            self._merge_contract_hints(
                self._variant_contract_hints(report_dir, object_text, manager_text),
                self._template_selection_contract_hints(name, variants, selection_infos, strategies),
                self._template_chart_variant_hints(report_dir, selection_infos, help_text),
                self._known_contract_hints(name, variants, strategies),
                self._historical_variant_hints(variants),
                self._prerequisite_empty_result_hints(variants, help_text),
            ),
        )
        primary_strategy = strategies[0] if strategies else {"kind": kind}
        aliases = [
            {
                "alias": entry["alias"],
                "source": entry.get("source", "template"),
                "variant": entry.get("variant") or self._variant_for_alias(entry["alias"], variants),
                "confidence": entry.get("confidence", 0.98),
            }
            for entry in template_entries
        ]
        aliases.extend(self._variant_aliases(variants))
        aliases.extend(self._known_aliases(name, variants))
        display_name = self._split_camel_display(name)
        if display_name != name:
            aliases.append({"alias": display_name, "source": "technical_display", "confidence": 0.72})
        aliases.append({"alias": name, "source": "technical", "confidence": 0.60})
        return {
            "name": name,
            "synonym": report_title,
            "source_path": str(report_dir),
            "kind": primary_strategy.get("kind", kind),
            "status": "supported" if strategies else "unsupported",
            "confidence": primary_strategy.get("confidence", 0.50),
            "diagnostics": {"exported_entrypoints": exported, "exported_functions": exported_functions, "graph": graph},
            "aliases": aliases,
            "variants": variants,
            "params": self._merge_params(self._params_for_known_report(name), template_params),
            "strategies": strategies,
            "output_contracts": output_contracts,
        }

    def _report_title(self, report_name: str, template_aliases: list[str], variants: list[dict]) -> str:
        for variant in variants:
            if str(variant.get("key") or "") == report_name:
                presentation = str(variant.get("presentation") or "").strip()
                if presentation:
                    return presentation
        display_name = self._split_camel_display(report_name).strip()
        if display_name and display_name != report_name:
            return display_name
        for alias in template_aliases:
            cleaned = str(alias or "").strip()
            if cleaned:
                return cleaned
        return report_name

    def _template_alias_entries(self, report_dir: Path) -> list[dict]:
        entries: list[dict] = []
        entries.extend(self._skd_variant_entries(report_dir))
        for xml_path in sorted((report_dir / "Templates").glob("*.xml")):
            text_aliases = self._xml_text_aliases(xml_path)
            template_type = self._template_type(xml_path)
            if text_aliases:
                entries.extend(
                    {
                        "alias": alias,
                        "source": "template",
                        "template": xml_path.stem,
                        "template_type": template_type,
                        "confidence": 0.98,
                    }
                    for alias in text_aliases
                )
            elif self._is_user_alias(xml_path.stem):
                entries.append(
                    {
                        "alias": xml_path.stem,
                        "source": "template_name",
                        "template": xml_path.stem,
                        "template_type": template_type,
                        "confidence": 0.82,
                    }
                )
        return self._unique_entries(entries)

    def _template_aliases(self, report_dir: Path) -> list[str]:
        return [entry["alias"] for entry in self._template_alias_entries(report_dir)]

    @staticmethod
    def _xml_text_aliases(path: Path) -> list[str]:
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except Exception:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            return ReportAnalyzer._unique_nonempty(
                [value for value in re.findall(r">([^<>]{4,80})<", raw) if ReportAnalyzer._is_user_alias(value)]
            )
        result = []
        for elem in root.iter():
            text = (elem.text or "").strip()
            if ReportAnalyzer._is_user_alias(text):
                result.append(text)
        return ReportAnalyzer._unique_nonempty(result)

    @staticmethod
    def _template_type(path: Path) -> str:
        match = _TEMPLATE_TYPE_RE.search(ReportAnalyzer._read_text(path))
        return match.group("value").strip() if match else ""

    @staticmethod
    def _is_skd_template_entry(entry: dict) -> bool:
        if entry.get("source") == "variant":
            return True
        return str(entry.get("template_type") or "").lower() == "datacompositionschema"

    def _classification_xml_text(self, report_dir: Path) -> str:
        paths = [*sorted((report_dir / "Templates").glob("*.xml")), *self._skd_template_ext_paths(report_dir)]
        return "\n".join(self._read_text(path) for path in self._unique_paths(paths))

    def _contract_template_xml_paths(self, report_dir: Path) -> list[Path]:
        return self._unique_paths([*sorted((report_dir / "Templates").glob("*.xml")), *self._contract_template_ext_paths(report_dir)])

    def _contract_template_ext_paths(self, report_dir: Path) -> list[Path]:
        skd_paths = set(self._skd_template_ext_paths(report_dir))
        result: list[Path] = []
        for xml_path in sorted((report_dir / "Templates").glob("*/Ext/Template.xml")):
            if xml_path in skd_paths:
                result.append(xml_path)
                continue
            try:
                if xml_path.stat().st_size <= _CONTRACT_LAYOUT_SIZE_LIMIT:
                    result.append(xml_path)
            except OSError:
                continue
        return self._unique_paths(result)

    def _skd_template_ext_paths(self, report_dir: Path) -> list[Path]:
        template_dir = report_dir / "Templates"
        template_types = {
            path.stem: self._template_type(path).lower()
            for path in sorted(template_dir.glob("*.xml"))
        }
        result: list[Path] = []
        for xml_path in sorted(template_dir.glob("*/Ext/Template.xml")):
            template_name = xml_path.parent.parent.name
            template_type = template_types.get(template_name, "")
            if template_type == "datacompositionschema":
                result.append(xml_path)
                continue
            if template_type:
                continue
            if self._sniff_skd_template(xml_path):
                result.append(xml_path)
        return result

    @staticmethod
    def _sniff_skd_template(xml_path: Path) -> bool:
        try:
            with xml_path.open("r", encoding="utf-8", errors="ignore") as handle:
                head = handle.read(131_072).lower()
        except OSError:
            return False
        return (
            "data-composition-system/schema" in head
            or "<settingsvariant" in head
            or "<dcsset:name" in head
            or "<dataset" in head
        )

    @staticmethod
    def _unique_paths(paths: list[Path]) -> list[Path]:
        result: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if path in seen:
                continue
            result.append(path)
            seen.add(path)
        return result

    def _skd_variant_entries(self, report_dir: Path) -> list[dict]:
        entries: list[dict] = []
        for xml_path in self._skd_template_ext_paths(report_dir):
            raw = self._read_text(xml_path)
            for match in _SKD_VARIANT_RE.finditer(raw):
                body = match.group("body")
                name_match = _SKD_NAME_RE.search(body)
                if not name_match:
                    continue
                key = name_match.group("name").strip()
                presentation = self._first_user_content(body)
                if presentation:
                    entries.append(
                        {
                            "alias": presentation,
                            "source": "variant",
                            "variant": key,
                            "template": xml_path.parent.parent.name,
                            "confidence": 0.99,
                        }
                    )
        return entries

    def _contract_texts(self, report_dir: Path) -> list[str]:
        values: list[str] = []
        for xml_path in self._contract_template_xml_paths(report_dir):
            values.extend(self._xml_text_aliases(xml_path))
        return self._unique_nonempty(values)

    def _template_text_catalog(self, report_dir: Path) -> dict[str, list[str]]:
        values: dict[str, list[str]] = {}
        for xml_path in self._contract_template_ext_paths(report_dir):
            values[xml_path.parent.parent.name] = self._xml_text_aliases(xml_path)
        for xml_path in sorted((report_dir / "Templates").glob("*.xml")):
            values.setdefault(xml_path.stem, self._xml_text_aliases(xml_path))
        return values

    def _variant_contract_hints(self, report_dir: Path, object_text: str, manager_text: str) -> dict[str, dict]:
        template_texts = self._template_text_catalog(report_dir)
        hints: dict[str, dict] = {}
        for match in _VARIANT_BRANCH_RE.finditer(object_text or ""):
            variant_key = str(match.group("variant") or "").strip()
            body = str(match.group("body") or "")
            if not variant_key:
                continue
            layout_match, layout_source = self._resolve_layout_source(body, object_text, manager_text)
            if not layout_match:
                continue
            layout_name = str(layout_match.group("layout") or "").strip()
            layout_texts = self._unique_nonempty(template_texts.get(layout_name) or [])
            if not layout_texts:
                continue
            visual_layout = self._looks_visual_layout(layout_source, layout_texts)
            markers = self._unique_nonempty([self._split_camel_display(report_dir.name), layout_texts[0], *layout_texts[:6]])
            hints[variant_key] = {
                "template_texts": layout_texts,
                "expected_columns": [],
                "expected_markers": markers,
                "expects_detail_rows": not visual_layout and not bool(re.search(r"\.Итог\s*>\s*0", layout_source, re.IGNORECASE)),
                "output_type": "mixed" if visual_layout else "rows",
                "allows_empty_result": bool(visual_layout or re.search(r"Если\s+ЗначениеЗаполнено\(", layout_source, re.IGNORECASE)),
                "expects_visual_components": visual_layout,
            }
        return hints

    def _template_chart_variant_hints(self, report_dir: Path, selection_infos: dict[str, dict[str, dict]], help_text: str) -> dict[str, dict]:
        hints: dict[str, dict] = {}
        prerequisite_empty_allowed = self._help_suggests_prerequisite_data(help_text)
        for xml_path in self._skd_template_ext_paths(report_dir):
            raw = self._read_text(xml_path)
            if "StructureItemChart" not in raw:
                continue
            template_name = xml_path.parent.parent.name
            template_selection = selection_infos.get(template_name) or {}
            for match in _SKD_VARIANT_RE.finditer(raw):
                body = str(match.group("body") or "")
                if "StructureItemChart" not in body:
                    continue
                name_match = _SKD_NAME_RE.search(body)
                if not name_match:
                    continue
                variant_key = name_match.group("name").strip()
                variant_info = template_selection.get(variant_key) or {}
                selected_fields = list(variant_info.get("selected_fields") or [])
                field_titles = dict(variant_info.get("field_titles") or {})
                expected_columns = [str(field_titles.get(field) or field).strip() for field in selected_fields if str(field_titles.get(field) or field).strip()]
                presentation = self._first_user_content(body) or self._split_camel_display(variant_key)
                hints[variant_key] = {
                    "expected_columns": self._unique_nonempty(expected_columns)[:12],
                    "expected_markers": self._unique_nonempty([presentation, *expected_columns[:4]]),
                    "output_type": "mixed",
                    "expects_detail_rows": False,
                    "allows_empty_result": prerequisite_empty_allowed,
                    "expects_visual_components": True,
                    "accepts_blank_output": prerequisite_empty_allowed,
                }
        return hints

    def _template_selection_contract_hints(
        self,
        report_name: str,
        variants: list[dict],
        selection_infos: dict[str, dict[str, dict]],
        strategies: list[dict],
    ) -> dict[str, dict]:
        hints: dict[str, dict] = {}
        for variant_item in variants or [{"key": "", "presentation": "", "template": ""}]:
            variant_key = str(variant_item.get("key") or "")
            if self._variant_uses_adapter_strategy(variant_key, strategies):
                continue
            template_name = str(variant_item.get("template") or "")
            template_selection = selection_infos.get(template_name) or {}
            variant_info = template_selection.get(variant_key) or template_selection.get("") or {}
            presented = self._unique_nonempty(list(variant_info.get("selected_presentations") or []))
            folder_titles = self._unique_nonempty(list(variant_info.get("folder_titles") or []))
            if not presented and not folder_titles:
                continue
            variant_title = str(variant_item.get("presentation") or self._split_camel_display(variant_key) or "").strip()
            hints[variant_key] = {
                "expected_columns": presented[:12],
                "expected_markers": self._unique_nonempty([variant_title, *folder_titles[:6], *presented[:6]]),
            }
        return hints

    def _known_contract_hints(self, report_name: str, variants: list[dict], strategies: list[dict]) -> dict[str, dict]:
        if report_name != "АнализНачисленийИУдержаний":
            return {}
        variant_key = self._preferred_payroll_variant(variants)
        if not variant_key or not self._variant_uses_adapter_strategy(variant_key, strategies):
            return {}
        markers = [
            "Расчетный листок",
            "Организация:",
            "Подразделение:",
            "Должность:",
            "Оклад (тариф):",
            "Начислено:",
            "Удержано:",
            "Выплачено:",
            "К выплате:",
        ]
        return {
            variant_key: {
                "report_title": "Расчетный листок",
                "expected_columns": [],
                "expected_markers": markers,
                "expects_detail_rows": True,
                "output_type": "rows",
            }
        }

    def _prerequisite_empty_result_hints(self, variants: list[dict], help_text: str) -> dict[str, dict]:
        if not self._help_suggests_prerequisite_data(help_text):
            return {}
        variant_items = variants or [{"key": ""}]
        return {
            str(item.get("key") or ""): {
                "allows_empty_result": True,
                "accepts_blank_output": True,
            }
            for item in variant_items
        }

    def _historical_variant_hints(self, variants: list[dict]) -> dict[str, dict]:
        hints: dict[str, dict] = {}
        for item in variants or [{"key": "", "presentation": ""}]:
            variant_key = str(item.get("key") or "")
            title = normalize_report_query(str(item.get("presentation") or ""))
            if "не актуал" not in title and not re.search(r"\bдо\s+20\d{2}\s+год", title):
                continue
            hints[variant_key] = {
                "allows_empty_result": True,
                "accepts_blank_output": True,
            }
        return hints

    @staticmethod
    def _report_help_text(report_dir: Path) -> str:
        html = ReportAnalyzer._read_text(report_dir / "Ext" / "Help" / "ru.html")
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", " ", html)
        return " ".join(text.split())

    @staticmethod
    def _help_suggests_prerequisite_data(help_text: str) -> bool:
        normalized = normalize_report_query(help_text)
        return (
            "предваритель" in normalized
            and "классификац" in normalized
            and ("регламентного задания" in normalized or "регламентные операции" in normalized)
        )

    def _merge_contract_hints(self, *items: dict[str, dict]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for hints in items:
            for variant_key, hint in (hints or {}).items():
                merged = dict(result.get(variant_key) or {})
                for key in ("template_texts", "expected_columns", "expected_markers"):
                    if key in hint and hint.get(key) == []:
                        merged[key] = []
                        continue
                    values = list(hint.get(key) or [])
                    if values:
                        merged[key] = self._unique_nonempty(list(merged.get(key) or []) + values)
                for key in ("output_type", "expects_detail_rows"):
                    if key in hint and hint.get(key) not in (None, ""):
                        merged[key] = hint.get(key)
                for key in ("report_title",):
                    if key in hint and str(hint.get(key) or "").strip():
                        merged[key] = str(hint.get(key) or "").strip()
                for key in ("allows_empty_result", "expects_visual_components", "accepts_blank_output"):
                    if key in hint:
                        merged[key] = bool(merged.get(key) or hint.get(key))
                result[variant_key] = merged
        return result

    def _resolve_layout_source(self, branch_body: str, object_text: str, manager_text: str) -> tuple[re.Match[str] | None, str]:
        queue = [branch_body]
        seen: set[str] = set()
        while queue:
            source = queue.pop(0)
            if not source or source in seen:
                continue
            seen.add(source)
            layout_match = _GET_LAYOUT_RE.search(source)
            if layout_match:
                return layout_match, source
            for call_match in _QUALIFIED_CALL_RE.finditer(source):
                function_body = self._function_body(manager_text, str(call_match.group("name") or "").strip())
                if function_body and function_body not in seen:
                    queue.append(function_body)
            for function_body in self._called_function_bodies(source, object_text, manager_text):
                if function_body and function_body not in seen:
                    queue.append(function_body)
        return None, branch_body

    @staticmethod
    def _function_body(module_text: str, function_name: str) -> str:
        if not module_text or not function_name:
            return ""
        pattern = re.compile(
            rf"\b(?:Функция|Процедура)\s+{re.escape(function_name)}\s*\([^)]*\)(?:\s+Экспорт)?(?P<body>.*?)(?:КонецФункции|КонецПроцедуры)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(module_text)
        return str(match.group("body") or "") if match else ""

    @staticmethod
    def _module_function_names(module_text: str) -> list[str]:
        return ReportAnalyzer._unique_nonempty([str(match.group("name") or "").strip() for match in _MODULE_MEMBER_RE.finditer(module_text or "")])

    def _called_function_bodies(self, branch_body: str, object_text: str, manager_text: str) -> list[str]:
        bodies: list[str] = []
        for module_text in (object_text, manager_text):
            for function_name in self._module_function_names(module_text):
                if not re.search(rf"\b{re.escape(function_name)}\s*\(", branch_body or "", re.IGNORECASE):
                    continue
                function_body = self._function_body(module_text, function_name)
                if function_body:
                    bodies.append(function_body)
        return bodies

    @staticmethod
    def _looks_visual_layout(module_text: str, layout_texts: list[str]) -> bool:
        lowered = (module_text or "").lower()
        if "диаграммаг" in lowered or "рисунки." in lowered:
            return True
        return any("диаграмм" in normalize_report_query(text) for text in layout_texts)

    def _output_contracts(
        self,
        report_name: str,
        report_title: str,
        kind: str,
        variants: list[dict],
        strategies: list[dict],
        template_texts: list[str],
        manager_text: str,
        object_text: str,
        variant_contract_hints: dict[str, dict] | None = None,
    ) -> list[dict]:
        variant_items = variants or [{"key": "", "presentation": report_title, "template": ""}]
        contracts = []
        for variant in variant_items:
            variant_key = str(variant.get("key") or "")
            variant_title = str(variant.get("presentation") or report_title or report_name)
            variant_strategies = [
                strategy
                for strategy in strategies
                if str(strategy.get("variant") or "") in {"", variant_key}
            ]
            hints = (variant_contract_hints or {}).get(variant_key, {})
            effective_report_title = str(hints.get("report_title") or report_title or report_name)
            contract_texts = list(hints.get("template_texts") or template_texts)
            expected_markers_override = None
            if "expected_markers" in hints:
                expected_markers_override = self._unique_nonempty(
                    [effective_report_title, variant_title, *(hints.get("expected_markers") or [])]
                )
            contracts.append(
                {
                    "variant": variant_key,
                    "source": "declared",
                    "contract": build_declared_output_contract(
                        report_name=report_name,
                        report_title=effective_report_title,
                        variant_key=variant_key,
                        variant_title=variant_title,
                        kind=kind,
                        strategies=variant_strategies,
                        template_texts=contract_texts,
                        manager_text=manager_text,
                        object_text=object_text,
                        expected_columns_override=hints.get("expected_columns"),
                        expected_markers_override=expected_markers_override,
                        expects_detail_rows=hints.get("expects_detail_rows"),
                        output_type_override=str(hints.get("output_type") or "") or None,
                        allows_empty_result=bool(hints.get("allows_empty_result")),
                        expects_visual_components=bool(hints.get("expects_visual_components")),
                        accepts_blank_output=bool(hints.get("accepts_blank_output")),
                    ),
                }
            )
        return contracts

    @staticmethod
    def _variant_uses_adapter_strategy(variant_key: str, strategies: list[dict]) -> bool:
        for strategy in strategies or []:
            if str(strategy.get("strategy") or "") != "adapter_entrypoint":
                continue
            if str(strategy.get("variant") or "") not in {"", variant_key}:
                continue
            return True
        return False

    def _variants(self, manager_text: str, template_entries: list[dict], report_dir: Path) -> list[dict]:
        presentations = self._skd_variant_presentations(report_dir)
        descriptions = self._manager_variant_descriptions(manager_text)
        variants: dict[str, dict] = {}
        manager_variant_keys = self._manager_variant_keys(manager_text)
        for key in manager_variant_keys:
            details = {"launchable": True, "variant_source": "manager"}
            if descriptions.get(key):
                details["description"] = descriptions[key]
            variants[key] = {
                "key": key,
                "presentation": presentations.get(key) or self._split_camel_display(key),
                "template": "",
                "details": details,
            }
        skd_template_entries = [entry for entry in template_entries if self._is_skd_template_entry(entry)]
        for entry in skd_template_entries:
            key = str(entry.get("variant") or "").strip()
            if key:
                existing = variants.get(key, {})
                details = dict(existing.get("details") or {})
                details["launchable"] = bool(details.get("launchable", not manager_variant_keys))
                details["variant_source"] = "manager_template" if key in manager_variant_keys else "template_only"
                variants[key] = {
                    "key": key,
                    "presentation": entry["alias"],
                    "template": str(entry.get("template") or ""),
                    "details": details,
                }
        if skd_template_entries and not variants:
            first = skd_template_entries[0]
            variants[first["alias"].replace(" ", "")] = {
                "key": first["alias"].replace(" ", ""),
                "presentation": first["alias"],
                "template": str(first.get("template") or first["alias"]),
                "details": {"launchable": True, "variant_source": "template_only"},
            }
        return list(variants.values())

    @staticmethod
    def _variant_for_alias(alias: str, variants: list[dict]) -> str:
        if not variants:
            return ""
        for variant in variants:
            if variant.get("presentation") == alias:
                return str(variant.get("key") or "")
        return str(variants[0].get("key") or "")

    @staticmethod
    def _exported_entrypoints(manager_text: str) -> list[str]:
        return _EXPORT_RE.findall(manager_text)

    @staticmethod
    def _exported_functions(manager_text: str) -> list[dict]:
        functions = []
        for match in _EXPORTED_FUNCTION_RE.finditer(manager_text):
            params = ReportAnalyzer._signature_params(match.group("params"))
            functions.append(
                {
                    "name": match.group("name"),
                    "params": params,
                    "required_params": len([param for param in params if not param.get("has_default")]),
                }
            )
        return functions

    @staticmethod
    def _signature_params(raw_params: str) -> list[dict]:
        params = []
        for raw in (raw_params or "").split(","):
            cleaned = " ".join(raw.replace("\n", " ").split()).strip()
            if not cleaned:
                continue
            without_default = cleaned.split("=", 1)[0].strip()
            name = without_default.split()[-1] if without_default.split() else ""
            params.append({"name": name, "has_default": "=" in cleaned})
        return params

    @staticmethod
    def _has_variant_setup(manager_text: str) -> bool:
        return bool(_VARIANT_CALL_RE.search(manager_text))

    @staticmethod
    def _manager_variant_keys(manager_text: str) -> list[str]:
        keys: list[str] = []
        for match in _VARIANT_CALL_RE.finditer(manager_text):
            quoted = re.findall(r'"([^"]+)"', match.group("args"))
            if quoted and ReportAnalyzer._is_variant_key(quoted[-1]):
                keys.append(quoted[-1])
        return ReportAnalyzer._unique_nonempty(keys)

    @staticmethod
    def _manager_variant_descriptions(manager_text: str) -> dict[str, str]:
        descriptions: dict[str, str] = {}
        for match in _VARIANT_CALL_RE.finditer(manager_text):
            quoted = re.findall(r'"([^"]+)"', match.group("args"))
            if not quoted or not ReportAnalyzer._is_variant_key(quoted[-1]):
                continue
            variant_key = quoted[-1]
            tail = manager_text[match.end(): match.end() + 2000]
            description_match = re.search(
                r'НастройкиВарианта\.Описание\s*=\s*НСтр\("(?P<body>.*?)"\)\s*;',
                tail,
                re.IGNORECASE | re.DOTALL,
            )
            if not description_match:
                continue
            ru_match = re.search(r"ru\s*=\s*'(?P<text>.*?)';", description_match.group("body"), re.IGNORECASE | re.DOTALL)
            if not ru_match:
                continue
            description = " ".join(ru_match.group("text").replace("|", " ").split())
            if description:
                descriptions[variant_key] = description
        return descriptions

    def _skd_variant_presentations(self, report_dir: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for xml_path in self._skd_template_ext_paths(report_dir):
            raw = self._read_text(xml_path)
            for match in _SKD_VARIANT_RE.finditer(raw):
                body = match.group("body")
                name_match = _SKD_NAME_RE.search(body)
                if not name_match:
                    continue
                presentation = self._first_user_content(body)
                if presentation:
                    result[name_match.group("name").strip()] = presentation
        return result

    @staticmethod
    def _first_user_content(text: str) -> str:
        for match in _XML_CONTENT_RE.finditer(text):
            value = match.group("value").strip()
            if ReportAnalyzer._is_user_alias(value):
                return value
        return ""

    @staticmethod
    def _classify(all_text: str, has_templates: bool, has_exported: bool) -> str:
        return ReportAnalyzer._classify_parts("", "", all_text, has_templates, has_exported)

    @staticmethod
    def _classify_parts(manager_text: str, object_text: str, xml_text: str, has_templates: bool, has_exported: bool) -> str:
        all_text = manager_text + "\n" + object_text + "\n" + xml_text
        lowered = all_text.lower()
        object_lowered = object_text.lower()
        xml_lowered = xml_text.lower()
        if "регламентированныйотчет" in lowered:
            return "form_or_regulated"
        if "внешниенаборыданных" in lowered or "externaldatasets" in lowered or ReportAnalyzer._has_external_dataset(xml_lowered):
            return "external_datasets_required"
        if ReportAnalyzer._needs_runtime_probe(object_lowered, xml_lowered):
            return "runtime_probe_required"
        if has_exported:
            return "exported_entrypoint_probe"
        if has_templates:
            return "raw_skd_runner"
        return "unsupported"

    @staticmethod
    def _needs_runtime_probe(object_text: str, xml_text: str) -> bool:
        if "текущаядатасеанса(" in xml_text:
            return True
        if "схемакомпоновкиданных.наборыданных" in object_text:
            return True
        if _BSL_TEMP_TABLE_RE.search(xml_text):
            return True
        if _BSL_MODULE_CALL_RE.search("\n".join(re.findall(r"<expression>(.*?)</expression>", xml_text, flags=re.IGNORECASE | re.DOTALL))):
            return True
        params = {
            match.group("name").lower()
            for match in _BSL_AMP_PARAM_RE.finditer(xml_text)
            if match.group("name").lower() not in _XML_ENTITY_NAMES
            and not match.group("name").startswith("#")
        }
        return bool(params - _SAFE_RAW_SKD_PARAMS)

    @staticmethod
    def _has_external_dataset(xml_text: str) -> bool:
        return "<dataset" in xml_text and "datasetobject" in xml_text and "<objectname>" in xml_text

    def _strategies(
        self,
        name: str,
        kind: str,
        variants: list[dict],
        root: Path,
        graph: dict,
        report_dir: Path,
        object_text: str,
        exported_functions: list[dict],
        has_variant_setup: bool,
    ) -> list[dict]:
        selection_infos = self._template_selection_infos(report_dir)
        launchable_variants = [
            variant_item
            for variant_item in variants
            if bool((variant_item.get("details") or {}).get("launchable", True))
        ]
        variant = str((launchable_variants or variants)[0].get("key") or "") if (launchable_variants or variants) else ""
        payroll_adapter_source = self._payroll_adapter_source(root, graph)
        if name == "АнализНачисленийИУдержаний" and payroll_adapter_source:
            variant = self._preferred_payroll_variant(variants)
            return [{
                "kind": "external_datasets_required",
                "strategy": "adapter_entrypoint",
                "priority": 10,
                "confidence": 0.99,
                "entrypoint": "ЗарплатаКадрыОтчеты.ДанныеРасчетныхЛистков",
                "output_type": "rows",
                "variant": variant,
                "requires_runtime_probe": False,
                "details": {"adapter": "payroll_sheet", "source": payroll_adapter_source},
            }]
        no_arg_entrypoints = self._preferred_no_arg_entrypoints(exported_functions)
        if kind == "exported_entrypoint_probe" and no_arg_entrypoints:
            return [
                {
                    "kind": kind,
                    "strategy": "manager_no_arg_function_runner",
                    "priority": 35 + index,
                    "confidence": 0.75,
                    "entrypoint": entrypoint,
                    "output_type": "rows",
                    "variant": "",
                    "requires_runtime_probe": True,
                    "details": {"function": entrypoint},
                }
                for index, entrypoint in enumerate(no_arg_entrypoints)
            ]
        forms = self._form_names(report_dir)
        if forms and (kind == "form_or_regulated" or name.lower().startswith("регламентирован") or not variants):
            return [{
                "kind": kind,
                "strategy": "form_artifact_runner",
                "priority": 30,
                "confidence": 0.60,
                "entrypoint": "",
                "output_type": "artifact",
                "variant": variant,
                "requires_runtime_probe": True,
                "blocked_reason": "requires_existing_object_ref",
                "details": {"forms": forms, "requires_object_ref": True},
            }]
        object_events = self._object_report_events(object_text)
        requires_object_ref = self._requires_object_ref_context(object_text)
        variant_items = launchable_variants or variants
        if object_events and not variant_items and has_variant_setup:
            variant_items = [{"key": "", "presentation": "", "template": ""}]
        if object_events and variant_items and kind in {
            "form_or_regulated",
            "raw_skd_runner",
            "runtime_probe_required",
            "external_datasets_required",
            "exported_entrypoint_probe",
        }:
            strategies = [
                {
                    "kind": kind,
                    "strategy": "bsp_variant_report_runner",
                    "priority": 25,
                    "confidence": 0.82,
                    "entrypoint": "ВариантыОтчетов.СформироватьОтчет",
                    "output_type": "rows",
                    "variant": str(variant_item.get("key") or ""),
                    "requires_runtime_probe": True,
                    "details": {
                        "template": str(variant_item.get("template") or ""),
                        "object_events": object_events,
                        "requires_object_ref": requires_object_ref,
                        **self._variant_shape_details(selection_infos, str(variant_item.get("template") or ""), str(variant_item.get("key") or "")),
                    },
                }
                for variant_item in variant_items
            ]
            if kind == "runtime_probe_required":
                strategies.extend(self._dataset_query_strategies(variant_items, report_dir))
            if kind != "raw_skd_runner":
                strategies.extend(self._attach_variant_shape_details(self._raw_probe_strategies(kind, variant_items), selection_infos))
            return strategies
        if kind == "raw_skd_runner":
            dataset_query_strategies = self._dataset_query_strategies(launchable_variants or variants, report_dir)
            fallback_strategies = [
                {
                    "kind": kind,
                    "strategy": "raw_skd_runner",
                    "priority": 50,
                    "confidence": 0.70,
                    "entrypoint": "",
                    "output_type": "rows",
                    "variant": str(variant_item.get("key") or ""),
                    "requires_runtime_probe": False,
                    "details": (
                        {
                            "template": str(variant_item.get("template") or ""),
                            **self._variant_shape_details(selection_infos, str(variant_item.get("template") or ""), str(variant_item.get("key") or "")),
                        }
                        if str(variant_item.get("template") or "")
                        else self._variant_shape_details(selection_infos, "", str(variant_item.get("key") or ""))
                    ),
                }
                for variant_item in (launchable_variants or variants)
            ]
            return dataset_query_strategies + fallback_strategies
        if kind in {"runtime_probe_required", "external_datasets_required", "exported_entrypoint_probe"} and (launchable_variants or variants):
            probe_strategies = self._raw_probe_strategies(kind, launchable_variants or variants)
            if kind == "runtime_probe_required":
                dataset_query_strategies = self._dataset_query_strategies(launchable_variants or variants, report_dir)
                return self._attach_variant_shape_details(dataset_query_strategies + probe_strategies, selection_infos)
            return self._attach_variant_shape_details(probe_strategies, selection_infos)
        return []

    @staticmethod
    def _raw_probe_strategies(kind: str, variants: list[dict]) -> list[dict]:
        return [
            {
                "kind": kind,
                "strategy": "raw_skd_probe_runner",
                "priority": 90,
                "confidence": 0.35,
                "entrypoint": "",
                "output_type": "rows",
                "variant": str(variant_item.get("key") or ""),
                "requires_runtime_probe": True,
                "blocked_reason": kind,
                "details": {"template": str(variant_item.get("template") or "")} if str(variant_item.get("template") or "") else {},
            }
            for variant_item in variants
        ]

    @staticmethod
    def _preferred_no_arg_entrypoints(exported_functions: list[dict]) -> list[str]:
        no_arg = [str(item.get("name") or "") for item in exported_functions if int(item.get("required_params") or 0) == 0]
        if not no_arg:
            return []
        preferred = [
            name
            for name in no_arg
            if any(marker in name.lower() for marker in ("информация", "представление", "данные", "получить"))
        ]
        return preferred or no_arg

    def _dataset_query_strategies(self, variants: list[dict], report_dir: Path) -> list[dict]:
        template_infos = self._dataset_query_template_infos(report_dir)
        strategies: list[dict] = []
        for variant_item in variants:
            template_name = str(variant_item.get("template") or "")
            info = template_infos.get(template_name)
            if not info:
                continue
            variant_key = str(variant_item.get("key") or "")
            raw_selected_fields = info["variant_fields"].get(variant_key) or info["default_fields"]
            dataset_fields = set(info["dataset_fields"] or [])
            selected_fields = [field for field in raw_selected_fields if field in dataset_fields]
            if not selected_fields:
                selected_fields = list(info["default_fields"])
            if not selected_fields:
                continue
            strategies.append(
                {
                    "kind": "raw_skd_runner",
                    "strategy": "raw_skd_dataset_query_runner",
                    "priority": 40,
                    "confidence": 0.84,
                    "entrypoint": "",
                    "output_type": "rows",
                    "variant": variant_key,
                    "requires_runtime_probe": False,
                    "details": {
                        "template": template_name,
                        "query_text": info["query_text"],
                        "data_set_name": info["dataset_name"],
                        "selected_fields": selected_fields,
                        "field_titles": {field: info["field_titles"].get(field, field) for field in selected_fields},
                    },
                }
            )
        return strategies

    def _dataset_query_template_infos(self, report_dir: Path) -> dict[str, dict]:
        infos: dict[str, dict] = {}
        for xml_path in self._skd_template_ext_paths(report_dir):
            info = self._dataset_query_template_info(xml_path)
            if info:
                infos[xml_path.parent.parent.name] = info
        return infos

    @staticmethod
    def _dataset_query_template_info(xml_path: Path) -> dict | None:
        raw = ReportAnalyzer._read_text(xml_path)
        if not raw.strip():
            return None
        try:
            root = ET.fromstring(raw)
        except Exception:
            return None
        ns = {
            "dcs": "http://v8.1c.ru/8.1/data-composition-system/schema",
            "dcsset": "http://v8.1c.ru/8.1/data-composition-system/settings",
            "v8": "http://v8.1c.ru/8.1/data/core",
        }
        xsi_type = "{http://www.w3.org/2001/XMLSchema-instance}type"
        local_sources = {
            (item.findtext("dcs:name", default="", namespaces=ns) or "").strip()
            for item in root.findall("dcs:dataSource", ns)
            if (item.findtext("dcs:dataSourceType", default="", namespaces=ns) or "").strip().lower() == "local"
        }
        datasets = []
        for item in root.findall("dcs:dataSet", ns):
            if not str(item.attrib.get(xsi_type) or "").endswith("DataSetQuery"):
                continue
            dataset_source = (item.findtext("dcs:dataSource", default="", namespaces=ns) or "").strip()
            if local_sources and dataset_source and dataset_source not in local_sources:
                continue
            query_text = (item.findtext("dcs:query", default="", namespaces=ns) or "").strip()
            if not query_text:
                continue
            field_titles: dict[str, str] = {}
            dataset_fields: list[str] = []
            for field_item in item.findall("dcs:field", ns):
                data_path = (field_item.findtext("dcs:dataPath", default="", namespaces=ns) or "").strip()
                if not data_path:
                    continue
                dataset_fields.append(data_path)
                title = (field_item.findtext(".//v8:content", default="", namespaces=ns) or "").strip()
                field_titles[data_path] = title or data_path
            datasets.append(
                {
                    "dataset_name": (item.findtext("dcs:name", default="", namespaces=ns) or "").strip(),
                    "query_text": query_text,
                    "field_titles": field_titles,
                    "dataset_fields": dataset_fields,
                }
            )
        if len(datasets) != 1:
            return None
        variant_info = ReportAnalyzer._template_selection_info(xml_path)
        variant_fields = {key: list(value.get("selected_fields") or []) for key, value in variant_info.items()}
        dataset = datasets[0]
        return {
            "dataset_name": dataset["dataset_name"],
            "query_text": dataset["query_text"],
            "field_titles": dataset["field_titles"],
            "dataset_fields": dataset["dataset_fields"],
            "default_fields": dataset["dataset_fields"],
            "variant_fields": variant_fields,
        }

    def _template_selection_infos(self, report_dir: Path) -> dict[str, dict[str, dict]]:
        infos: dict[str, dict[str, dict]] = {}
        for xml_path in self._skd_template_ext_paths(report_dir):
            info = self._template_selection_info(xml_path)
            if info:
                infos[xml_path.parent.parent.name] = info
        return infos

    @staticmethod
    def _template_selection_info(xml_path: Path) -> dict[str, dict]:
        raw = ReportAnalyzer._read_text(xml_path)
        if not raw.strip():
            return {}
        try:
            root = ET.fromstring(raw)
        except Exception:
            return {}
        ns = {
            "dcs": "http://v8.1c.ru/8.1/data-composition-system/schema",
            "dcsset": "http://v8.1c.ru/8.1/data-composition-system/settings",
            "v8": "http://v8.1c.ru/8.1/data/core",
        }
        xsi_type = "{http://www.w3.org/2001/XMLSchema-instance}type"
        field_titles: dict[str, str] = {}
        for field_item in list(root.findall(".//dcs:field", ns)) + list(root.findall(".//dcs:calculatedField", ns)):
            data_path = (field_item.findtext("dcs:dataPath", default="", namespaces=ns) or "").strip()
            if not data_path:
                continue
            title = ReportAnalyzer._element_local_title(field_item, ns)
            if title:
                field_titles[data_path] = title
        variant_info: dict[str, dict] = {}
        for variant in root.findall(".//dcs:settingsVariant", ns):
            variant_key = (variant.findtext("dcsset:name", default="", namespaces=ns) or "").strip()
            if not variant_key:
                continue
            selected_fields: list[str] = []
            selected_presentations: list[str] = []
            folder_titles: list[str] = []
            for selection in variant.findall(".//dcsset:selection", ns):
                for selected in selection.findall("dcsset:item", ns):
                    ReportAnalyzer._collect_selected_items(
                        selected,
                        ns,
                        xsi_type,
                        field_titles,
                        selected_fields,
                        selected_presentations,
                        folder_titles,
                    )
            selected_fields = ReportAnalyzer._unique_nonempty([field for field in selected_fields if field])
            selected_presentations = ReportAnalyzer._unique_nonempty([title for title in selected_presentations if title])
            folder_titles = ReportAnalyzer._unique_nonempty([title for title in folder_titles if title])
            filter_fields: list[str] = []
            filter_titles: dict[str, str] = {}
            for filter_item in variant.findall(".//dcsset:filter/dcsset:item", ns):
                field_name = (filter_item.findtext("dcsset:left", default="", namespaces=ns) or "").strip()
                if not field_name:
                    field_name = (filter_item.findtext("dcsset:field", default="", namespaces=ns) or "").strip()
                if not field_name:
                    continue
                filter_fields.append(field_name)
                filter_title = ReportAnalyzer._element_local_title(filter_item, ns)
                filter_titles[field_name] = filter_title or filter_titles.get(field_name, field_name)
            filter_fields = ReportAnalyzer._unique_nonempty([field for field in filter_fields if field])
            if selected_fields or filter_fields:
                variant_info[variant_key] = {
                    "selected_fields": selected_fields,
                    "field_titles": {field: field_titles.get(field, field) for field in selected_fields},
                    "selected_presentations": selected_presentations,
                    "folder_titles": folder_titles,
                    "filter_fields": filter_fields,
                    "filter_titles": {field: filter_titles.get(field, field) for field in filter_fields},
                }
        return variant_info

    @staticmethod
    def _variant_shape_details(selection_infos: dict[str, dict[str, dict]], template_name: str, variant_key: str) -> dict:
        template_info = selection_infos.get(template_name) or {}
        variant_info = template_info.get(variant_key) or template_info.get("") or {}
        details: dict[str, object] = {}
        selected_fields = list(variant_info.get("selected_fields") or [])
        field_titles = dict(variant_info.get("field_titles") or {})
        selected_presentations = list(variant_info.get("selected_presentations") or [])
        folder_titles = list(variant_info.get("folder_titles") or [])
        filter_fields = list(variant_info.get("filter_fields") or [])
        filter_titles = dict(variant_info.get("filter_titles") or {})
        if selected_fields:
            details["selected_fields"] = selected_fields
        if field_titles:
            details["field_titles"] = field_titles
        if selected_presentations:
            details["selected_presentations"] = selected_presentations
        if folder_titles:
            details["folder_titles"] = folder_titles
        if filter_fields:
            details["filter_fields"] = filter_fields
        if filter_titles:
            details["filter_titles"] = filter_titles
        return details

    @staticmethod
    def _element_local_title(item: ET.Element, ns: dict[str, str]) -> str:
        for title_path in ("dcs:title", "dcsset:lwsTitle", "dcsset:presentation"):
            title_item = item.find(title_path, ns)
            if title_item is not None:
                title = ReportAnalyzer._local_string_text(title_item, ns)
                if title:
                    return title
        return ReportAnalyzer._local_string_text(item, ns)

    @staticmethod
    def _local_string_text(item: ET.Element, ns: dict[str, str]) -> str:
        fallback = ""
        for local_item in item.findall(".//v8:item", ns):
            value = (local_item.findtext("v8:content", default="", namespaces=ns) or "").strip()
            if not value:
                continue
            lang = (local_item.findtext("v8:lang", default="", namespaces=ns) or "").strip().lower()
            if lang == "ru":
                return value
            if not fallback:
                fallback = value
        for content in item.findall(".//v8:content", ns):
            value = str(content.text or "").strip()
            if value and not fallback:
                fallback = value
        return fallback

    @staticmethod
    def _collect_selected_items(
        item: ET.Element,
        ns: dict[str, str],
        xsi_type: str,
        field_titles: dict[str, str],
        selected_fields: list[str],
        selected_presentations: list[str],
        folder_titles: list[str],
    ) -> None:
        item_type = str(item.attrib.get(xsi_type) or "")
        if item_type.endswith("SelectedItemFolder"):
            folder_title = ReportAnalyzer._element_local_title(item, ns)
            if folder_title:
                folder_titles.append(folder_title)
            for child in item.findall("dcsset:item", ns):
                ReportAnalyzer._collect_selected_items(
                    child,
                    ns,
                    xsi_type,
                    field_titles,
                    selected_fields,
                    selected_presentations,
                    folder_titles,
                )
            return
        if item_type.endswith("SelectedItemField"):
            field_name = (item.findtext("dcsset:field", default="", namespaces=ns) or "").strip()
            if not field_name:
                return
            selected_fields.append(field_name)
            title = ReportAnalyzer._element_local_title(item, ns)
            selected_presentations.append(title or field_titles.get(field_name, field_name))

    def _template_params(self, report_dir: Path) -> list[dict]:
        params: list[dict] = []
        for xml_path in self._skd_template_ext_paths(report_dir):
            params.extend(self._template_variant_params(xml_path))
        return self._merge_params([], params)

    def _template_variant_params(self, xml_path: Path) -> list[dict]:
        raw = self._read_text(xml_path)
        if not raw.strip():
            return []
        try:
            root = ET.fromstring(raw)
        except Exception:
            return []
        ns = {
            "dcs": "http://v8.1c.ru/8.1/data-composition-system/schema",
            "dcsset": "http://v8.1c.ru/8.1/data-composition-system/settings",
            "dcscor": "http://v8.1c.ru/8.1/data-composition-system/core",
            "v8": "http://v8.1c.ru/8.1/data/core",
        }
        definitions = self._parameter_definitions(root, ns)
        params: list[dict] = []
        for variant in root.findall(".//dcs:settingsVariant", ns):
            variant_key = (variant.findtext("dcsset:name", default="", namespaces=ns) or "").strip()
            if not variant_key:
                continue
            for item in variant.findall(".//dcsset:dataParameters/dcscor:item", ns):
                name = (item.findtext("dcscor:parameter", default="", namespaces=ns) or "").strip()
                if not name or name == "ВариантОтчета":
                    continue
                definition = definitions.get(name, {})
                value_node = next((child for child in item if child.tag.endswith("value")), None)
                default_value = self._xml_value(value_node)
                if default_value is None:
                    default_value = definition.get("default")
                params.append(
                    {
                        "variant": variant_key,
                        "name": name,
                        "presentation": str(definition.get("presentation") or name),
                        "type_name": str(definition.get("type_name") or ""),
                        "required": bool(definition.get("required") and default_value is None),
                        "default": default_value,
                        "source": "skd_variant_data_parameter",
                    }
                )
        return params

    def _parameter_definitions(self, root: ET.Element, ns: dict[str, str]) -> dict[str, dict[str, Any]]:
        definitions: dict[str, dict[str, Any]] = {}
        for item in root.findall("dcs:parameter", ns):
            name = (item.findtext("dcs:name", default="", namespaces=ns) or item.findtext("name", default="") or "").strip()
            if not name:
                continue
            presentation = (
                item.findtext(".//v8:content", default="", namespaces=ns)
                or item.findtext("dcs:title//v8:content", default="", namespaces=ns)
                or item.findtext("title", default="")
                or name
            ).strip()
            type_names = [
                str(type_node.text or "").strip().split(":", 1)[-1]
                for type_node in item.findall(".//v8:Type", ns)
                if str(type_node.text or "").strip()
            ]
            if not type_names:
                type_id = (item.findtext(".//v8:TypeId", default="", namespaces=ns) or "").strip()
                if type_id:
                    type_names = [type_id]
            value_node = next((child for child in item if child.tag.endswith("value")), None)
            definitions[name] = {
                "presentation": presentation,
                "type_name": "|".join(type_names),
                "required": ((item.findtext("dcs:use", default="", namespaces=ns) or item.findtext("use", default="") or "").strip().lower() == "always"),
                "default": self._xml_value(value_node),
            }
        return definitions

    @staticmethod
    def _xml_value(value_node: ET.Element | None) -> Any:
        if value_node is None:
            return None
        xsi_nil = value_node.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil")
        if str(xsi_nil or "").lower() == "true":
            return None
        xsi_type = str(value_node.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type") or "").lower()
        text = "".join(value_node.itertext()).strip()
        if not text:
            return None
        if xsi_type.endswith("boolean"):
            return text.lower() == "true"
        if xsi_type.endswith("decimal"):
            try:
                return int(text) if text.isdigit() else float(text)
            except ValueError:
                return text
        if xsi_type.endswith("datetime"):
            return text
        if "standardbeginningdate" in xsi_type:
            return {"kind": "standard_beginning_date", "value": text}
        return text

    @staticmethod
    def _merge_params(base_params: list[dict], extra_params: list[dict]) -> list[dict]:
        merged: dict[tuple[str, str], dict] = {}
        for param in list(base_params or []) + list(extra_params or []):
            name = str(param.get("name") or "").strip()
            if not name:
                continue
            key = (str(param.get("variant") or ""), name)
            if key not in merged or str(param.get("source") or "").startswith("skd_"):
                merged[key] = dict(param)
        return sorted(
            merged.values(),
            key=lambda item: (str(item.get("variant") or ""), 0 if item.get("required") else 1, str(item.get("name") or "")),
        )

    def _attach_variant_shape_details(self, strategies: list[dict], selection_infos: dict[str, dict[str, dict]]) -> list[dict]:
        enriched = []
        for strategy in strategies:
            details = dict(strategy.get("details") or {})
            details.update(
                self._variant_shape_details(
                    selection_infos,
                    str(details.get("template") or ""),
                    str(strategy.get("variant") or ""),
                )
            )
            enriched.append({**strategy, "details": details})
        return enriched

    def _attach_variant_details(self, variants: list[dict], selection_infos: dict[str, dict[str, dict]]) -> list[dict]:
        enriched = []
        for variant in variants:
            details = dict(variant.get("details") or {})
            details.update(
                self._variant_shape_details(
                    selection_infos,
                    str(variant.get("template") or ""),
                    str(variant.get("key") or ""),
                )
            )
            enriched.append({**variant, "details": details})
        return enriched

    @staticmethod
    def _object_report_events(object_text: str) -> list[str]:
        events = []
        for event in (
            "ОпределитьНастройкиФормы",
            "ПередЗагрузкойНастроекВКомпоновщик",
            "ПриСозданииНаСервере",
            "ПриКомпоновкеРезультата",
        ):
            if re.search(rf"\b(?:Процедура|Функция)\s+{re.escape(event)}\b", object_text, re.IGNORECASE):
                events.append(event)
        return events

    @staticmethod
    def _requires_object_ref_context(object_text: str) -> bool:
        lowered = object_text.lower()
        if "параметркоманды" not in lowered:
            return False
        return any(
            marker in lowered
            for marker in (
                "предназначен только для открытия",
                "только для открытия в документе",
                "открытия в документе",
                "формапараметры.отбор",
                "регистратор",
            )
        )

    @staticmethod
    def _form_names(report_dir: Path) -> list[str]:
        forms_dir = report_dir / "Forms"
        if not forms_dir.exists():
            return []
        return [path.name for path in sorted(forms_dir.iterdir()) if path.is_dir()]

    @staticmethod
    def _template_for_variant(variant_key: str, variants: list[dict]) -> str:
        for variant in variants:
            if str(variant.get("key") or "") == variant_key:
                return str(variant.get("template") or "")
        return ""

    @staticmethod
    def _has_payroll_adapter(root: Path) -> bool:
        module = root / "CommonModules" / "ЗарплатаКадрыОтчеты" / "Ext" / "Module.bsl"
        return "ДанныеРасчетныхЛистков" in ReportAnalyzer._read_text(module)

    def _payroll_adapter_source(self, root: Path, graph: dict) -> str:
        if self._has_payroll_adapter(root):
            return "static"
        candidates = graph.get("adapter_candidates") or []
        if any(candidate.get("name") == "ЗарплатаКадрыОтчеты" for candidate in candidates):
            return "graph"
        return ""

    @staticmethod
    def _preferred_payroll_variant(variants: list[dict]) -> str:
        for variant in variants:
            key = str(variant.get("key") or "")
            if key == "РасчетныйЛисток":
                return key
        for variant in variants:
            key = str(variant.get("key") or "")
            presentation = str(variant.get("presentation") or "")
            if normalize_report_query(key) == "расчетный листок":
                return key
            if normalize_report_query(presentation) == "расчетный листок":
                return key
        return str(variants[0].get("key") or "") if variants else ""

    def _graph_summary(self, report_name: str) -> dict:
        nodes = list(self.graph_hints.get("nodes") or [])
        edges = list(self.graph_hints.get("edges") or [])
        node_ids = []
        adapter_candidates = []
        report_name_lower = report_name.lower()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            node_name = str(props.get("name") or node.get("name") or "")
            node_id = str(node.get("id") or "")
            if report_name_lower and report_name_lower in (node_id + " " + node_name).lower():
                node_ids.append(node_id)
            if node_name == "ЗарплатаКадрыОтчеты":
                adapter_candidates.append({"name": node_name, "id": node_id, "type": node.get("type")})
        related_edge_count = 0
        node_id_set = set(node_ids)
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("sourceId") in node_id_set or edge.get("targetId") in node_id_set:
                related_edge_count += 1
        return {
            "available": bool(self.graph_hints.get("available")),
            "node_ids": node_ids[:20],
            "related_edge_count": related_edge_count,
            "adapter_candidates": adapter_candidates[:20],
            "error": str(self.graph_hints.get("error") or ""),
        }

    @staticmethod
    def _params_for_known_report(name: str) -> list[dict]:
        if name != "АнализНачисленийИУдержаний":
            return []
        return [
            {"name": "Сотрудник", "presentation": "Сотрудник", "type_name": "СправочникСсылка.Сотрудники", "source": "adapter"},
            {"name": "Организация", "presentation": "Организация", "type_name": "СправочникСсылка.Организации", "source": "adapter"},
        ]

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    @staticmethod
    def _unique_nonempty(values: list[str]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            cleaned = " ".join(str(value).split())
            if cleaned and cleaned not in seen:
                result.append(cleaned)
                seen.add(cleaned)
        return result

    @staticmethod
    def _unique_entries(entries: list[dict]) -> list[dict]:
        result = []
        seen = set()
        for entry in entries:
            alias = " ".join(str(entry.get("alias") or "").split())
            if not alias:
                continue
            key = (alias, str(entry.get("variant") or ""))
            if key in seen:
                continue
            copy = dict(entry)
            copy["alias"] = alias
            result.append(copy)
            seen.add(key)
        return result

    @staticmethod
    def _variant_aliases(variants: list[dict]) -> list[dict]:
        aliases = []
        for variant in variants:
            key = str(variant.get("key") or "")
            presentation = str(variant.get("presentation") or "")
            if presentation and ReportAnalyzer._is_user_alias(presentation):
                aliases.append({"alias": presentation, "source": "variant", "variant": key, "confidence": 0.95})
            display = ReportAnalyzer._split_camel_display(key)
            if display and display != presentation and ReportAnalyzer._is_user_alias(display):
                aliases.append({"alias": display, "source": "variant_key", "variant": key, "confidence": 0.88})
        return aliases

    @staticmethod
    def _known_aliases(name: str, variants: list[dict]) -> list[dict]:
        if name != "АнализНачисленийИУдержаний":
            return []
        preferred = ""
        for variant in variants:
            key = str(variant.get("key") or "")
            presentation = str(variant.get("presentation") or "")
            if key == "РасчетныйЛисток" or normalize_report_query(key) == "расчетный листок":
                preferred = key
                break
            if normalize_report_query(presentation) == "расчетный листок":
                preferred = key
                break
        return [
            {"alias": "Расчетный листок", "source": "known_adapter", "variant": preferred, "confidence": 1.0},
            {"alias": "Расчётный листок", "source": "known_adapter", "variant": preferred, "confidence": 1.0},
            {"alias": "Расчетные листки", "source": "known_adapter", "variant": preferred, "confidence": 0.96},
        ]

    @staticmethod
    def _is_user_alias(value: str) -> bool:
        cleaned = " ".join(str(value or "").split())
        if not 3 <= len(cleaned) <= 120:
            return False
        normalized = cleaned.replace("ё", "е").lower()
        compact = re.sub(r"[^0-9a-zа-я]+", "", normalized, flags=re.IGNORECASE)
        if normalized in _SERVICE_ALIASES or compact in _SERVICE_ALIASES:
            return False
        if cleaned.startswith("http") or any(char in cleaned for char in ("\n", "\r", "{", "}", "<", ">", ";", "=")):
            return False
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
            return False
        return bool(re.search(r"[А-Яа-яЁё]", cleaned))

    @staticmethod
    def _is_variant_key(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9_]+", value or ""))

    @staticmethod
    def _split_camel_display(value: str) -> str:
        parts = re.sub(r"(?<=[0-9a-zа-яё])(?=[A-ZА-ЯЁ])", " ", value or "")
        return " ".join(parts.split())
