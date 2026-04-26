"""Static analyzer for 1C report metadata exported to BSL/XML files."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .report_catalog import ReportCatalog, normalize_report_query


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
_SAFE_RAW_SKD_PARAMS = {
    "дата",
    "датаначала",
    "датаконца",
    "датаокончания",
    "конецпериода",
    "началопериода",
    "период",
}
_SERVICE_ALIASES = {
    "data composition schema",
    "datacompositionschema",
    "основная схема компоновки данных",
    "основнаясхемакомпоновкиданных",
}


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
        variants = self._variants(manager_text, template_entries, report_dir)
        exported = self._exported_entrypoints(manager_text)
        exported_functions = self._exported_functions(manager_text)
        xml_text = "\n".join(self._read_text(path) for path in report_dir.rglob("*.xml"))
        kind = self._classify_parts(manager_text, object_text, xml_text, has_skd_templates, bool(exported))
        graph = self._graph_summary(name)
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
            "synonym": template_aliases[0] if template_aliases else name,
            "source_path": str(report_dir),
            "kind": primary_strategy.get("kind", kind),
            "status": "supported" if strategies else "unsupported",
            "confidence": primary_strategy.get("confidence", 0.50),
            "diagnostics": {"exported_entrypoints": exported, "exported_functions": exported_functions, "graph": graph},
            "aliases": aliases,
            "variants": variants,
            "params": self._params_for_known_report(name),
            "strategies": strategies,
        }

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

    def _skd_variant_entries(self, report_dir: Path) -> list[dict]:
        entries: list[dict] = []
        for xml_path in sorted((report_dir / "Templates").glob("*/Ext/Template.xml")):
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

    def _variants(self, manager_text: str, template_entries: list[dict], report_dir: Path) -> list[dict]:
        presentations = self._skd_variant_presentations(report_dir)
        variants: dict[str, dict] = {}
        for key in self._manager_variant_keys(manager_text):
            variants[key] = {
                "key": key,
                "presentation": presentations.get(key) or self._split_camel_display(key),
                "template": "",
            }
        skd_template_entries = [entry for entry in template_entries if self._is_skd_template_entry(entry)]
        for entry in skd_template_entries:
            key = str(entry.get("variant") or "").strip()
            if key:
                variants[key] = {
                    "key": key,
                    "presentation": entry["alias"],
                    "template": str(entry.get("template") or ""),
                }
        if skd_template_entries and not variants:
            first = skd_template_entries[0]
            variants[first["alias"].replace(" ", "")] = {
                "key": first["alias"].replace(" ", ""),
                "presentation": first["alias"],
                "template": str(first.get("template") or first["alias"]),
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

    def _skd_variant_presentations(self, report_dir: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for xml_path in sorted((report_dir / "Templates").glob("*/Ext/Template.xml")):
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
        params = {match.group("name").lower() for match in _BSL_AMP_PARAM_RE.finditer(xml_text)}
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
        variant = str(variants[0].get("key") or "") if variants else ""
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
        variant_items = variants
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
                    },
                }
                for variant_item in variant_items
            ]
            if kind != "raw_skd_runner":
                strategies.extend(self._raw_probe_strategies(kind, variants))
            return strategies
        if kind == "raw_skd_runner":
            return [
                {
                    "kind": kind,
                    "strategy": "raw_skd_runner",
                    "priority": 50,
                    "confidence": 0.70,
                    "entrypoint": "",
                    "output_type": "rows",
                    "variant": str(variant_item.get("key") or ""),
                    "requires_runtime_probe": False,
                    "details": {"template": str(variant_item.get("template") or "")} if str(variant_item.get("template") or "") else {},
                }
                for variant_item in variants
            ]
        if kind in {"runtime_probe_required", "external_datasets_required", "exported_entrypoint_probe"} and variants:
            return self._raw_probe_strategies(kind, variants)
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
