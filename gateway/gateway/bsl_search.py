"""
Full-text search over BSL source files.
Indexes exported 1C configuration BSL files and provides
semantic search for finding BSP functions, procedures, and code patterns.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Regex for procedure/function declarations
_PROC_RE = re.compile(
    r'^(Процедура|Функция|Procedure|Function)\s+(\w+)\s*\(([^)]*)\)(\s+Экспорт|\s+Export)?',
    re.MULTILINE | re.IGNORECASE,
)
# Region comment
_REGION_RE = re.compile(r'^#Область\s+(.+)', re.MULTILINE)
# Comment block above proc
_COMMENT_RE = re.compile(r'((?://[^\n]*\n)+)')


@dataclass
class BslSymbol:
    name: str
    kind: str  # "Процедура" or "Функция"
    params: str
    export: bool
    file: str
    module: str  # e.g. "ОбщийМодуль.ОбщегоНазначения"
    line: int
    comment: str = ""


class BslSearchIndex:
    """In-memory index of BSL symbols for full-text search."""

    def __init__(self) -> None:
        self._symbols: list[BslSymbol] = []
        self._indexed_path: str = ""

    @property
    def indexed(self) -> bool:
        return bool(self._symbols)

    @property
    def symbol_count(self) -> int:
        return len(self._symbols)

    def build_index(self, bsl_root: str, container: str = "") -> str:
        """Index all BSL files. If container is set, use docker exec to read from LSP container."""
        if container:
            return self._build_index_docker(container, bsl_root)

        root = Path(bsl_root)
        if not root.exists():
            return f"ERROR: Directory {bsl_root} does not exist."

        self._symbols.clear()
        bsl_files = list(root.rglob("*.bsl"))
        if not bsl_files:
            return f"ERROR: No BSL files found in {bsl_root}."

        for bsl_file in bsl_files:
            try:
                self._index_file(bsl_file, root)
            except Exception as exc:
                log.debug(f"Error indexing {bsl_file}: {exc}")

        self._indexed_path = bsl_root
        log.info(f"BSL index built: {len(self._symbols)} symbols from {len(bsl_files)} files")
        return f"Indexed {len(self._symbols)} symbols from {len(bsl_files)} BSL files in {bsl_root}."

    def _build_index_docker(self, container: str, bsl_root: str = "/projects") -> str:
        """Index BSL files via docker exec grep — fast, no file-by-file reads."""
        self._symbols.clear()
        try:
            # Single grep to extract all proc/func declarations with file/line info
            result = subprocess.run(
                [
                    "docker", "exec", container,
                    "grep", "-rn",
                    "--include=*.bsl",
                    "-E", r"^(Процедура|Функция|Procedure|Function)\s+\w+\s*\(",
                    bsl_root,
                ],
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: grep timed out after 120s."
        except Exception as exc:
            return f"ERROR: {exc}"

        if not result.stdout.strip():
            return f"ERROR: No BSL symbols found in {container}:{bsl_root}."

        root_prefix = bsl_root.rstrip("/") + "/"
        file_count = set()
        for line in result.stdout.strip().split("\n"):
            # Format: /projects/CommonModules/Mod/Ext/Module.bsl:42:Функция Имя(Параметры) Экспорт
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            filepath = parts[0]
            try:
                line_num = int(parts[1])
            except ValueError:
                continue
            decl = parts[2].strip()

            match = _PROC_RE.match(decl)
            if not match:
                continue

            rel_path = filepath[len(root_prefix):] if filepath.startswith(root_prefix) else filepath
            file_count.add(rel_path)
            rel_parts = tuple(rel_path.split("/"))
            module = self._derive_module_name(rel_parts)

            self._symbols.append(BslSymbol(
                name=match.group(2),
                kind=match.group(1).capitalize(),
                params=match.group(3).strip()[:200] if match.group(3) else "",
                export=bool(match.group(4)),
                file=rel_path,
                module=module,
                line=line_num,
            ))

        self._indexed_path = f"{container}:{bsl_root}"
        log.info(f"BSL index built (docker): {len(self._symbols)} symbols from {len(file_count)} files")
        return f"Indexed {len(self._symbols)} symbols from {len(file_count)} BSL files in {container}:{bsl_root}."

    def _index_file(self, filepath: Path, root: Path) -> None:
        """Extract procedures/functions from a BSL file."""
        try:
            text = filepath.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            return

        # Derive module name from path
        rel = filepath.relative_to(root)
        parts = rel.parts
        module = self._derive_module_name(parts)

        for match in _PROC_RE.finditer(text):
            kind = match.group(1)
            name = match.group(2)
            params = match.group(3).strip()
            export = bool(match.group(4))
            line = text[:match.start()].count("\n") + 1

            # Extract preceding comments
            comment = ""
            before = text[:match.start()]
            comment_match = _COMMENT_RE.search(before[-500:] if len(before) > 500 else before)
            if comment_match:
                raw = comment_match.group(1)
                comment = "\n".join(
                    ln.lstrip("/").strip() for ln in raw.strip().split("\n")
                )[:300]

            self._symbols.append(BslSymbol(
                name=name,
                kind=kind.capitalize(),
                params=params[:200],
                export=export,
                file=str(rel),
                module=module,
                line=line,
                comment=comment,
            ))

    def _derive_module_name(self, parts: tuple[str, ...]) -> str:
        """Derive 1C module name from file path parts."""
        # CommonModules/МойМодуль/Ext/Module.bsl → ОбщийМодуль.МойМодуль
        # Documents/МойДок/Ext/ObjectModule.bsl → Документ.МойДок.МодульОбъекта
        type_map = {
            "CommonModules": "ОбщийМодуль",
            "Catalogs": "Справочник",
            "Documents": "Документ",
            "DataProcessors": "Обработка",
            "Reports": "Отчет",
            "InformationRegisters": "РегистрСведений",
            "AccumulationRegisters": "РегистрНакопления",
            "AccountingRegisters": "РегистрБухгалтерии",
            "CommonForms": "ОбщаяФорма",
            "Enums": "Перечисление",
            "ChartsOfCharacteristicTypes": "ПВХ",
            "ChartsOfAccounts": "ПланСчетов",
            "ExchangePlans": "ПланОбмена",
            "BusinessProcesses": "БизнесПроцесс",
            "Tasks": "Задача",
            "Constants": "Константа",
        }
        if len(parts) >= 2:
            folder = parts[0]
            obj_name = parts[1]
            prefix = type_map.get(folder, folder)
            return f"{prefix}.{obj_name}"
        return ".".join(parts[:-1]) if parts else ""

    def search(self, query: str, limit: int = 20, export_only: bool = False) -> list[dict]:
        """Search symbols by name, module, or comment text."""
        if not self._symbols:
            return []

        query_lower = query.lower()
        query_words = query_lower.split()
        results: list[tuple[int, BslSymbol]] = []

        for sym in self._symbols:
            if export_only and not sym.export:
                continue

            score = 0
            name_lower = sym.name.lower()
            module_lower = sym.module.lower()
            comment_lower = sym.comment.lower()

            # Exact name match
            if query_lower == name_lower:
                score += 100
            # Name starts with query
            elif name_lower.startswith(query_lower):
                score += 50
            # Name contains query
            elif query_lower in name_lower:
                score += 30
            # Module contains query
            elif query_lower in module_lower:
                score += 20
            # Comment contains query
            elif query_lower in comment_lower:
                score += 10
            # Multi-word: all words match somewhere
            elif all(w in name_lower or w in module_lower or w in comment_lower for w in query_words):
                score += 15
            else:
                continue

            # Bonus for export
            if sym.export:
                score += 5

            results.append((score, sym))

        results.sort(key=lambda x: -x[0])
        return [
            {
                "name": sym.name,
                "kind": sym.kind,
                "params": sym.params,
                "export": sym.export,
                "module": sym.module,
                "file": sym.file,
                "line": sym.line,
                "comment": sym.comment,
                "score": score,
            }
            for score, sym in results[:limit]
        ]


# Singleton
bsl_search = BslSearchIndex()
