from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from mcp.types import CallToolResult, Tool
from mcp.types import TextContent

from ..bsl_search import BslSearchIndex
from ..config import settings
from .base import BackendBase

logger = logging.getLogger(__name__)

_RENAME_FILE_RE = re.compile(r"^File:\s+.+$")
_RENAME_URI_RE = re.compile(r"^\s*URI:\s+(file://\S+)\s*$")
_RENAME_EDIT_RE = re.compile(
    r'^\s*\d+\.\s+Line\s+(\d+)\s+\(chars\s+(\d+)-(\d+)\):\s+Replace with\s+"((?:[^"\\]|\\.)*)"\s*$'
)


@dataclass(frozen=True)
class _RenameEdit:
    line: int
    start_char: int
    end_char: int
    replacement: str


@dataclass(frozen=True)
class _RenameFileEdits:
    uri: str
    edits: tuple[_RenameEdit, ...]


def _parse_rename_preview(text: str) -> list[_RenameFileEdits]:
    files: list[_RenameFileEdits] = []
    current_uri: str | None = None
    current_edits: list[_RenameEdit] = []

    for raw_line in text.splitlines():
        if _RENAME_FILE_RE.match(raw_line):
            if current_uri is not None:
                files.append(_RenameFileEdits(uri=current_uri, edits=tuple(current_edits)))
            current_uri = None
            current_edits = []
            continue

        uri_match = _RENAME_URI_RE.match(raw_line)
        if uri_match:
            current_uri = uri_match.group(1)
            continue

        edit_match = _RENAME_EDIT_RE.match(raw_line)
        if edit_match:
            replacement = json.loads(f'"{edit_match.group(4)}"')
            current_edits.append(
                _RenameEdit(
                    line=int(edit_match.group(1)),
                    start_char=int(edit_match.group(2)),
                    end_char=int(edit_match.group(3)),
                    replacement=replacement,
                )
            )

    if current_uri is not None:
        files.append(_RenameFileEdits(uri=current_uri, edits=tuple(current_edits)))

    return files


def _apply_rename_preview_to_text(text: str, edits: tuple[_RenameEdit, ...]) -> str:
    lines = text.splitlines(keepends=True)
    sorted_edits = sorted(edits, key=lambda item: (item.line, item.start_char), reverse=True)

    for edit in sorted_edits:
        line_index = edit.line - 1
        if line_index < 0 or line_index >= len(lines):
            raise ValueError(f"rename edit points outside file: line {edit.line}")

        original_line = lines[line_index]
        content_only = original_line.rstrip("\r\n")
        newline = original_line[len(content_only):]

        if edit.start_char < 0 or edit.end_char < edit.start_char or edit.end_char > len(content_only):
            raise ValueError(
                f"rename edit range is invalid for line {edit.line}: {edit.start_char}-{edit.end_char}"
            )

        updated_line = (
            content_only[: edit.start_char]
            + edit.replacement
            + content_only[edit.end_char :]
        )
        lines[line_index] = updated_line + newline

    return "".join(lines)


class DockerControlLspBackend(BackendBase):
    """LSP backend proxied through the internal docker-control sidecar."""

    def __init__(self, name: str, slug: str, control_url: str | None = None, project_path: str | None = None):
        super().__init__(name)
        self._slug = slug
        self._control_url = (control_url or settings.docker_control_url).rstrip("/")
        self._project_path = (project_path or "").strip()
        self._symbol_search_index = BslSearchIndex()

    def _project_root_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self._project_path:
            candidates.append(Path(self._project_path))

        workspace_root = Path((settings.bsl_workspace or "/workspace").strip() or "/workspace")
        if self._slug:
            candidates.append(workspace_root / self._slug)
            default_workspace = Path("/workspace") / self._slug
            if default_workspace not in candidates:
                candidates.append(default_workspace)
            for hostfs_root in self._hostfs_workspace_roots():
                candidate = hostfs_root / self._slug
                if candidate not in candidates:
                    candidates.append(candidate)

        return candidates

    def _hostfs_workspace_roots(self) -> list[Path]:
        host_workspace = str(getattr(settings, "bsl_host_workspace", "") or "").strip()
        if not host_workspace:
            return []

        raw_root = Path(host_workspace)
        if not raw_root.is_absolute():
            return []
        if host_workspace.startswith("/home/"):
            return [Path("/hostfs-home").joinpath(*raw_root.parts[2:])]
        return [raw_root]

    def _headers(self) -> dict[str, str]:
        token = (settings.docker_control_token or "").strip()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    async def _start_locked(self) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self._control_url}/api/lsp-proxy/start",
                json={"slug": self._slug},
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "docker-control LSP start failed")
        self.tools = [Tool(**item) for item in payload.get("tools", [])]
        self.available = True

    async def start(self) -> None:
        async with self._lock:
            await self._start_locked()
        logger.info("[%s] connected (%s tools) via docker-control", self.name, len(self.tools))

    async def stop(self) -> None:
        async with self._lock:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.post(
                        f"{self._control_url}/api/lsp-proxy/stop",
                        json={"slug": self._slug},
                        headers=self._headers(),
                    )
            except Exception:
                pass
            self.available = False
            self.tools = []

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        async with self._lock:
            if not self.available:
                await self._start_locked()
            try:
                if name == "symbol_explore":
                    return await self._call_symbol_explore_with_fallback(arguments)
                if name == "rename" and str(arguments.get("apply", "")).lower() == "true":
                    return await self._call_rename_with_local_apply(arguments)
                return await self._call_tool_once(name, arguments)
            except Exception as exc:
                logger.warning("[%s] call_tool failed (%s), reconnecting...", self.name, exc)
                await self._start_locked()
                logger.info("[%s] reconnected (%s tools)", self.name, len(self.tools))
                if name == "symbol_explore":
                    return await self._call_symbol_explore_with_fallback(arguments)
                if name == "rename" and str(arguments.get("apply", "")).lower() == "true":
                    return await self._call_rename_with_local_apply(arguments)
                return await self._call_tool_once(name, arguments)

    def _symbol_search_roots(self) -> list[str]:
        roots: list[str] = []
        seen: set[str] = set()
        for candidate in self._project_root_candidates():
            normalized = str(candidate).strip()
            if normalized and normalized not in seen:
                roots.append(normalized)
                seen.add(normalized)
        container_root = f"mcp-lsp-{self._slug}:/projects"
        if container_root not in seen:
            roots.append(container_root)
        return roots

    def _symbol_explore_fallback(self, arguments: dict) -> CallToolResult:
        query = str(arguments.get("query") or "").strip()
        limit_raw = arguments.get("limit", 20)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 100))
        export_only = str(arguments.get("export_only") or "").strip().lower() in {"1", "true", "yes"}

        loaded = False
        for root in self._symbol_search_roots():
            if self._symbol_search_index.ensure_loaded(root):
                loaded = True
                break

        if not loaded:
            raise RuntimeError("symbol_explore fallback could not load a BSL index for the active project")

        results = self._symbol_search_index.search(query, limit=limit, export_only=export_only)
        payload = json.dumps(results, ensure_ascii=False, indent=2)
        return CallToolResult(content=[TextContent(type="text", text=payload)], isError=False)

    async def _call_symbol_explore_with_fallback(self, arguments: dict) -> CallToolResult:
        try:
            return await asyncio.wait_for(self._call_tool_once("symbol_explore", arguments), timeout=15)
        except Exception as exc:
            logger.warning(
                "[%s] symbol_explore live call failed (%s), using cached/local fallback",
                self.name,
                exc,
            )
            return self._symbol_explore_fallback(arguments)

    def _project_file_from_uri(self, uri: str) -> Path:
        prefix = "file:///projects/"
        if not uri.startswith(prefix):
            raise RuntimeError(f"Unsupported rename URI outside /projects: {uri}")
        relative = uri[len(prefix) :]
        if not relative or ".." in relative.split("/"):
            raise RuntimeError(f"Unsafe rename URI: {uri}")
        candidates = self._project_root_candidates()
        if not candidates:
            raise RuntimeError("project_path is not configured for local rename apply")
        probeable_candidates: list[tuple[Path, bool]] = []
        for root in candidates:
            try:
                probeable_candidates.append((root, root.exists()))
            except OSError as exc:
                logger.debug("Skipping inaccessible rename root candidate %s: %s", root, exc)
                continue
        existing_target = next(
            (
                root / relative
                for root, exists in probeable_candidates
                if exists and (root / relative).exists()
            ),
            None,
        )
        if existing_target is not None:
            return existing_target
        existing_root = next((root for root, exists in probeable_candidates if exists), None)
        root = existing_root or (probeable_candidates[0][0] if probeable_candidates else candidates[0])
        return root / relative

    def _relative_project_path_from_uri(self, uri: str) -> str:
        prefix = "file:///projects/"
        if not uri.startswith(prefix):
            raise RuntimeError(f"Unsupported rename URI outside /projects: {uri}")
        relative = uri[len(prefix) :]
        if not relative or ".." in relative.split("/"):
            raise RuntimeError(f"Unsafe rename URI: {uri}")
        return relative

    async def _write_project_file_via_runtime(self, relative_path: str, content: str) -> None:
        container_name = f"mcp-lsp-{self._slug}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self._control_url}/api/lsp/write-file",
                headers=self._headers(),
                json={
                    "container_name": container_name,
                    "relative_path": relative_path,
                    "content": content,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok", True):
                raise RuntimeError(payload.get("error") or "lsp write-file failed")

    async def _call_rename_with_local_apply(self, arguments: dict) -> CallToolResult:
        preview_args = dict(arguments)
        preview_args["apply"] = "false"
        preview = await self._call_tool_once("rename", preview_args)
        preview_text = "\n".join(getattr(item, "text", str(item)) for item in preview.content)
        file_edits = _parse_rename_preview(preview_text)
        if not file_edits:
            raise RuntimeError("rename preview did not include editable file operations")

        for file_edit in file_edits:
            target = self._project_file_from_uri(file_edit.uri)
            relative_path = self._relative_project_path_from_uri(file_edit.uri)
            original = target.read_text(encoding="utf-8-sig")
            updated = _apply_rename_preview_to_text(original, file_edit.edits)
            try:
                target.write_text(updated, encoding="utf-8-sig")
            except PermissionError:
                await self._write_project_file_via_runtime(relative_path, updated)

        if any(tool.name == "did_change_watched_files" for tool in self.tools):
            await self._call_tool_once("did_change_watched_files", {"language": "bsl", "changes_json": "[]"})

        result_text = preview_text.rstrip() + "\n\nRENAME APPLIED\nAll rename changes have been applied across the codebase."
        return CallToolResult(content=[TextContent(type="text", text=result_text)], isError=False)

    async def _call_tool_once(self, name: str, arguments: dict) -> CallToolResult:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self._control_url}/api/lsp-proxy/call",
                json={"slug": self._slug, "name": name, "arguments": arguments},
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "docker-control LSP call failed")
        return CallToolResult(**payload["result"])
