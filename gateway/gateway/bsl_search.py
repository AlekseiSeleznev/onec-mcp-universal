"""
Full-text search over BSL source files.
Indexes exported 1C configuration BSL files and provides
semantic search for finding BSP functions, procedures, and code patterns.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import subprocess
import httpx
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def _default_cache_dir() -> Path:
    data_dir = Path("/data")
    if data_dir.exists():
        return data_dir / "bsl-search-cache"
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "onec-gateway" / "bsl-search-cache"

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
        self._cache_dir = _default_cache_dir()
        self._lock = threading.RLock()

    @property
    def indexed(self) -> bool:
        with self._lock:
            return bool(self._symbols)

    @property
    def symbol_count(self) -> int:
        with self._lock:
            return len(self._symbols)

    @property
    def indexed_path(self) -> str:
        with self._lock:
            return self._indexed_path

    def _snapshot_path(self, bsl_root: str) -> Path:
        key = sha256(bsl_root.encode("utf-8")).hexdigest()[:24]
        return self._cache_dir / f"{key}.json"

    def _save_snapshot(self, bsl_root: str) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {
                    "indexed_path": bsl_root,
                    "symbols": [sym.__dict__ for sym in self._symbols],
                }
            self._snapshot_path(bsl_root).write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning(f"Failed to save BSL search snapshot for {bsl_root}: {exc}")

    def load_index(self, bsl_root: str) -> bool:
        snapshot = self._snapshot_path(bsl_root)
        if not snapshot.exists():
            return False
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            symbols = payload.get("symbols", [])
            parsed_symbols = [BslSymbol(**item) for item in symbols]
            with self._lock:
                self._symbols = parsed_symbols
                self._indexed_path = payload.get("indexed_path", bsl_root)
                return bool(self._symbols)
        except Exception as exc:
            log.warning(f"Failed to load BSL search snapshot for {bsl_root}: {exc}")
            return False

    def _load_compatible_snapshot(self, bsl_root: str) -> bool:
        """Load a snapshot for the same DB basename when the exact root changed."""
        requested_name = self._snapshot_match_name(bsl_root)
        if not requested_name or not self._cache_dir.exists():
            return False

        candidates: list[tuple[float, Path]] = []
        for snapshot in self._cache_dir.glob("*.json"):
            try:
                payload = json.loads(snapshot.read_text(encoding="utf-8"))
            except Exception:
                continue
            indexed_path = str(payload.get("indexed_path") or "").rstrip("/")
            if self._snapshot_match_name(indexed_path) != requested_name:
                continue
            try:
                mtime = snapshot.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((mtime, snapshot))

        for _, snapshot in sorted(candidates, key=lambda item: item[0], reverse=True):
            try:
                payload = json.loads(snapshot.read_text(encoding="utf-8"))
                symbols = payload.get("symbols", [])
                parsed_symbols = [BslSymbol(**item) for item in symbols]
                with self._lock:
                    self._symbols = parsed_symbols
                    self._indexed_path = str(payload.get("indexed_path") or bsl_root)
                    return bool(self._symbols)
            except Exception as exc:
                log.warning(f"Failed to load compatible BSL snapshot from {snapshot}: {exc}")
        return False

    def _snapshot_match_name(self, bsl_root: str) -> str:
        normalized = (bsl_root or "").rstrip("/")
        if not normalized:
            return ""

        container = ""
        path_part = normalized
        if ":" in normalized and not normalized.startswith("/"):
            container, _, path_part = normalized.partition(":")

        match_name = Path(path_part or "").name
        if match_name and match_name not in {"projects", "workspace"}:
            return match_name

        for prefix in ("mcp-lsp-", "onec-toolkit-", "mcp-toolkit-"):
            if container.startswith(prefix):
                suffix = container[len(prefix):].strip()
                if suffix:
                    return suffix

        return match_name

    def ensure_loaded(self, bsl_root: str) -> bool:
        with self._lock:
            if self._indexed_path == bsl_root and bool(self._symbols):
                return True
        if self.load_index(bsl_root):
            return True
        if self._load_compatible_snapshot(bsl_root):
            return True

        root = Path(bsl_root)
        try:
            root_exists = root.exists()
        except PermissionError:
            # gateway (uid 10001) may fail to traverse /home/user/* with mode 750;
            # let build_index resolve it via docker-control.
            root_exists = True
        if root_exists:
            result = self.build_index(bsl_root)
            return not result.startswith("ERROR")
        return False

    def clear(self) -> None:
        """Drop the in-memory index for the currently loaded project."""
        with self._lock:
            self._symbols.clear()
            self._indexed_path = ""

    def invalidate_paths(self, *paths: str) -> bool:
        """Clear the loaded index and on-disk snapshots when they match supplied roots."""
        normalized = {(path or "").rstrip("/") for path in paths if (path or "").strip()}
        if not normalized:
            return False

        matched = False
        if self._indexed_path.rstrip("/") in normalized:
            self.clear()
            matched = True

        for path in normalized:
            snapshot = self._snapshot_path(path)
            try:
                snapshot.unlink()
                matched = True
            except FileNotFoundError:
                continue
            except Exception as exc:
                log.warning(f"Failed to remove BSL search snapshot for {path}: {exc}")

        return matched

    def _gateway_visible_root(self, bsl_root: str) -> str:
        """Translate legacy container-style roots to a gateway-readable local path."""
        normalized = (bsl_root or "").rstrip("/")
        if not normalized:
            return "/workspace"
        if ":" in normalized and not normalized.startswith("/"):
            _, _, suffix = normalized.partition(":")
            if suffix:
                normalized = suffix.rstrip("/")
        if normalized == "/projects":
            return "/workspace"
        if normalized.startswith("/projects/"):
            return "/workspace/" + normalized[len("/projects/"):]
        return normalized

    def _container_bsl_root(self, bsl_root: str) -> str:
        normalized = (bsl_root or "").rstrip("/")
        if not normalized:
            return "/projects"
        if normalized == "/projects" or normalized.startswith("/projects/"):
            return normalized
        return "/projects"

    def _docker_control_url(self) -> str:
        env_val = (os.environ.get("DOCKER_CONTROL_URL") or "").strip().rstrip("/")
        if env_val:
            return env_val
        try:
            from .config import settings as _s
            return (_s.docker_control_url or "").rstrip("/")
        except Exception:
            return ""

    def _docker_control_token(self) -> str:
        env_val = (os.environ.get("DOCKER_CONTROL_TOKEN") or "").strip()
        if env_val:
            return env_val
        try:
            from .config import settings as _s
            return (_s.docker_control_token or "").strip()
        except Exception:
            return ""

    def _parse_container_grep_output(self, output: str, container: str, bsl_root: str) -> str:
        if not output.strip():
            return f"ERROR: No BSL symbols found in {container}:{bsl_root}."

        symbols: list[BslSymbol] = []
        matched_files: set[str] = set()
        for raw_line in output.splitlines():
            parts = raw_line.split(":", 2)
            if len(parts) != 3:
                continue
            file_path, line_str, declaration = parts
            try:
                line_no = int(line_str)
            except ValueError:
                continue
            match = _PROC_RE.match(declaration)
            if not match:
                continue

            rel = file_path[len(bsl_root) :].lstrip("/") if file_path.startswith(bsl_root) else file_path.lstrip("/")
            rel_path = Path(rel)
            module = self._derive_module_name(rel_path.parts)
            matched_files.add(str(rel_path))
            symbols.append(
                BslSymbol(
                    name=match.group(2),
                    kind=match.group(1).capitalize(),
                    params=(match.group(3) or "").strip()[:200],
                    export=bool(match.group(4)),
                    file=str(rel_path),
                    module=module,
                    line=line_no,
                    comment="",
                )
            )

        indexed_key = f"{container}:{bsl_root}"
        with self._lock:
            self._symbols = symbols
            self._indexed_path = indexed_key
            self._save_snapshot(indexed_key)
        return (
            f"Indexed {len(symbols)} symbols from {len(matched_files)} "
            f"BSL files in {container}:{bsl_root}."
        )

    def _build_index_via_docker_control(self, container: str, bsl_root: str = "/projects") -> str | None:
        base_url = self._docker_control_url()
        if not base_url:
            return None

        headers = {}
        token = self._docker_control_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = httpx.post(
                f"{base_url}/api/lsp/index-bsl",
                json={"container": container, "bsl_root": bsl_root},
                headers=headers,
                timeout=120,
            )
        except Exception:
            return None

        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.status_code != 200 or not data.get("ok"):
            error = data.get("error") or f"docker-control returned HTTP {resp.status_code}"
            return f"ERROR: {error}"

        return self._parse_container_grep_output(str(data.get("output") or ""), container, bsl_root)

    def build_index(self, bsl_root: str, container: str = "") -> str:
        """Index all BSL files from a gateway-readable path."""
        local_root = self._gateway_visible_root(bsl_root)
        root = Path(local_root)
        # Python 3.12+ may raise PermissionError from Path.exists() when an
        # intermediate directory is not traversable by the gateway container
        # user (e.g. /home/as 750 when gateway runs as uid 10001). Fall back to
        # the LSP container via docker-control when available — that container
        # mounts the workspace directly and can read it as root.
        try:
            root_exists = root.exists()
        except PermissionError:
            if container:
                return self._build_index_docker(container, self._container_bsl_root(bsl_root))
            if self._load_compatible_snapshot(bsl_root):
                return (
                    f"Indexed {len(self._symbols)} symbols from cached snapshot for {local_root}."
                )
            return (
                f"ERROR: Permission denied accessing {local_root}. "
                "Verify export file permissions for the gateway user."
            )

        if not root_exists:
            if container:
                return self._build_index_docker(container, self._container_bsl_root(bsl_root))
            return f"ERROR: Directory {local_root} does not exist."

        symbols: list[BslSymbol] = []
        try:
            bsl_files = list(root.rglob("*.bsl"))
        except PermissionError as exc:
            if container:
                return self._build_index_docker(container, self._container_bsl_root(bsl_root))
            if self._load_compatible_snapshot(bsl_root):
                return (
                    f"Indexed {len(self._symbols)} symbols from cached snapshot for {local_root}."
                )
            return (
                f"ERROR: Permission denied listing BSL files in {local_root}. "
                "Verify export file permissions for the gateway user."
            )
        if not bsl_files:
            if container:
                return self._build_index_docker(container, self._container_bsl_root(bsl_root))
            if self._load_compatible_snapshot(bsl_root):
                return (
                    f"Indexed {len(self._symbols)} symbols from cached snapshot for {local_root}."
                )
            return f"ERROR: No BSL files found in {local_root}."

        permission_errors = 0
        for bsl_file in bsl_files:
            try:
                self._index_file(bsl_file, root, symbols)
            except PermissionError as exc:
                permission_errors += 1
                log.warning(f"Permission denied indexing {bsl_file}: {exc}")
            except Exception as exc:
                log.debug(f"Error indexing {bsl_file}: {exc}")

        if not symbols and permission_errors:
            return (
                f"ERROR: Permission denied reading {permission_errors} BSL files in {local_root}. "
                "Verify export file permissions for the gateway user."
            )

        indexed_key = f"{container}:{local_root}" if container else local_root
        with self._lock:
            self._symbols = symbols
            self._indexed_path = indexed_key
            self._save_snapshot(indexed_key)
        log.info(f"BSL index built: {len(symbols)} symbols from {len(bsl_files)} files")
        return f"Indexed {len(symbols)} symbols from {len(bsl_files)} BSL files in {local_root}."

    def _build_index_docker(self, container: str, bsl_root: str = "/projects") -> str:
        """Compatibility path kept for tests and dev fallbacks."""
        via_sidecar = self._build_index_via_docker_control(container, bsl_root)
        if via_sidecar is not None:
            return via_sidecar

        try:
            proc = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "sh",
                    "-lc",
                    (
                        "find "
                        f"'{bsl_root}' "
                        "-type f -name '*.bsl' -print0 | "
                        "xargs -0 -r grep -nHE "
                        "\"^(Процедура|Функция|Procedure|Function)[[:space:]]+\""
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: grep timed out after 120s."
        except Exception as exc:
            return f"ERROR: {exc}"

        return self._parse_container_grep_output(proc.stdout or "", container, bsl_root)

    def _index_file(self, filepath: Path, root: Path, symbols: list[BslSymbol] | None = None) -> None:
        """Extract procedures/functions from a BSL file."""
        try:
            text = filepath.read_text(encoding="utf-8-sig", errors="replace")
        except PermissionError:
            raise
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

            target = self._symbols if symbols is None else symbols
            target.append(BslSymbol(
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
        with self._lock:
            symbols = list(self._symbols)
        if not symbols:
            return []

        query_lower = query.lower()
        query_words = query_lower.split()
        results: list[tuple[int, BslSymbol]] = []

        for sym in symbols:
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
