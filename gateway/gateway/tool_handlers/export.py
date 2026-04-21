"""Handlers for BSL export helpers."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import httpx


def find_1cv8_binaries(base_dir: Path | None = None) -> dict[str, Path]:
    """Scan platform directory for installed 1cv8 thick client binaries."""
    base = base_dir or Path("/opt/1cv8/x86_64")
    result: dict[str, Path] = {}
    if not base.exists():
        return result

    for ver_dir in base.iterdir():
        if ver_dir.is_dir():
            v8 = ver_dir / "1cv8"
            if v8.exists():
                result[ver_dir.name] = v8
    return result


def pick_1cv8(
    preferred_version: str = "",
    find_binaries: Callable[[], dict[str, Path]] | None = None,
) -> Path | None:
    """Pick best 1cv8 binary: preferred version first, then newest available."""
    finder = find_binaries or find_1cv8_binaries
    available = finder()
    if not available:
        return None
    if preferred_version and preferred_version in available:
        return available[preferred_version]
    return available[sorted(available.keys(), reverse=True)[0]]


class SettingsLike(Protocol):
    """Minimal settings shape used by export handlers."""

    bsl_export_timeout: int
    bsl_workspace: str
    bsl_host_workspace: str
    export_host_url: str
    allow_container_designer_export: bool
    port: int
    platform_path: str


class ManagerLike(Protocol):
    """Minimal manager shape used by export handlers."""

    def has_tool(self, name: str) -> bool: ...
    async def call_tool(self, name: str, arguments: dict): ...


class ActiveDbRef(Protocol):
    """Minimal active DB shape used for LSP container lookup."""

    lsp_container: str


class ConnectionDbResolver(Protocol):
    """Resolve DB runtime info from a 1C connection string."""

    def __call__(self, connection: str) -> ActiveDbRef | None: ...


def _gateway_visible_host_path(host_path: str) -> str:
    """Map host paths under /home into the gateway's shared /hostfs-home mount."""
    normalized = (host_path or "").rstrip("/").rstrip("\\")
    if normalized == "/home":
        return "/hostfs-home"
    if normalized.startswith("/home/"):
        return "/hostfs-home/" + normalized[len("/home/") :]
    return host_path


def _container_fallback_index_path(path: str) -> str:
    """Force container-only indexing for gateway-specific mount paths."""
    normalized = (path or "").rstrip("/").rstrip("\\")
    if normalized in {"/hostfs-home", "/workspace", "/projects"}:
        return "/projects"
    for prefix in ("/hostfs-home/", "/workspace/", "/projects/"):
        if normalized.startswith(prefix):
            return "/projects"
    return path


def _summarize_index_result(index_result: str) -> str | None:
    """Extract a short human-readable summary from build_index() output."""
    raw = (index_result or "").replace("\ufeff", "").strip()
    if not raw or raw.startswith("ERROR"):
        return None

    for pattern in (
        r"(\d+)\s+symbols",
        r"(\d+)\s+символ(?:ов|а)?",
        r"Indexed\s+(\d+)",
        r"Проиндексировано\s+(\d+)",
    ):
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1)} символов"
    return raw


def _extract_bsl_file_count(raw_result: str) -> int | None:
    """Extract BSL file count from export-host/local export messages."""
    raw = (raw_result or "").replace("\ufeff", "").strip()
    match = re.search(r"(\d+)\s+BSL files", raw, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _is_zero_symbol_summary(summary: str | None) -> bool:
    normalized = (summary or "").replace("\ufeff", "").strip().lower()
    return normalized in {"0 symbols", "0 символов"}


def _extract_symbol_count(summary: str | None) -> int | None:
    normalized = (summary or "").replace("\ufeff", "").strip()
    if not normalized:
        return None
    match = re.search(r"(\d+)\s+(?:symbols|символ(?:ов|а)?)", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _is_implausibly_small_symbol_summary(
    summary: str | None,
    *,
    expected_file_count: int | None,
) -> bool:
    file_count = expected_file_count or 0
    if file_count < 100:
        return False

    symbol_count = _extract_symbol_count(summary)
    if symbol_count is None or symbol_count <= 0:
        return False

    # Large mature exports should surface far more than a handful of symbols.
    # Keep the threshold intentionally low for smaller projects but high enough
    # to reject transient partial trees like "1/2 symbols" on 10k+ files.
    minimum_stable_symbols = max(10, min(200, file_count // 50))
    return symbol_count < minimum_stable_symbols


def _existing_bsl_file_count(output_dir: str) -> int:
    """Count already available BSL files in an export tree."""
    root = Path(output_dir)
    if not root.is_dir():
        return 0
    try:
        return sum(1 for _ in root.rglob("*.bsl"))
    except Exception:
        return 0


def _auth_hint_message(raw_result: str) -> str:
    """Return a clearer action hint for auth-related Designer export failures."""
    return (
        f"Export failed: {raw_result}\n\n"
        "Для выгрузки через 1cv8 DESIGNER укажите учётные данные базы в MCPToolkit.epf:\n"
        "- поле «ПользовательBSL»\n"
        "- поле «ПарольBSL»"
    )


def _is_license_error(raw_result: str) -> bool:
    normalized = (raw_result or "").replace("\ufeff", "").strip().lower()
    return "license not found" in normalized or "не найдена лицензия" in normalized


async def _reuse_existing_export_tree(
    *,
    connection: str,
    output_dir: str,
    build_index: Callable[[str, str], str],
    active_db: ActiveDbRef | None,
    index_jobs: dict,
    logger,
    existing_file_count: int | None = None,
    fallback_reason: str = "",
) -> str:
    """Build index from an already existing export tree when fresh export is unavailable."""
    if existing_file_count is None:
        existing_file_count = _existing_bsl_file_count(output_dir)
    index_jobs[connection] = {"status": "running", "result": ""}
    index_ok, index_result = await _finalize_index_result(
        output_dir=output_dir,
        build_index=build_index,
        active_db=active_db,
        logger=logger,
        expected_file_count=existing_file_count,
    )
    if index_ok:
        index_jobs[connection] = {"status": "done", "result": index_result}
        if fallback_reason:
            if existing_file_count <= 0 and _is_zero_symbol_summary(index_result):
                index_jobs[connection] = {"status": "error", "result": index_result}
                return f"ERROR: {index_result}"
            if existing_file_count > 0:
                return f"Выгрузка завершена: {existing_file_count} BSL файлов. Индекс: {index_result}."
            return (
                f"Свежая выгрузка недоступна ({fallback_reason}). "
                f"Использован сохранённый BSL индекс. Индекс: {index_result}."
            )
        return f"Выгрузка завершена: {existing_file_count} BSL файлов. Индекс: {index_result}."

    index_jobs[connection] = {"status": "error", "result": index_result}
    return index_result


async def _finalize_index_result(
    *,
    output_dir: str,
    build_index: Callable[[str, str], str],
    active_db: ActiveDbRef | None,
    logger,
    expected_file_count: int | None = None,
    retry_delays: tuple[float, ...] = (1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 60.0),
) -> tuple[bool, str]:
    """
    Build BSL index and retry once-stable exports that transiently report tiny counts.

    Real host-side exports can report ``status=done`` before the gateway sees fully
    durable file contents. When a large export immediately yields ``0 symbols`` or
    another implausibly small symbol count on the first pass, wait briefly and retry
    before treating the result as final.
    """
    index_ok, index_result = build_index_with_fallback(
        output_dir,
        build_index=build_index,
        active_db=active_db,
    )
    if not index_ok:
        return index_ok, index_result

    if not _is_zero_symbol_summary(index_result) and not _is_implausibly_small_symbol_summary(
        index_result,
        expected_file_count=expected_file_count,
    ):
        return index_ok, index_result

    if (expected_file_count or 0) < 100:
        return index_ok, index_result

    last_ok = index_ok
    last_result = index_result
    for delay in retry_delays:
        if _is_zero_symbol_summary(last_result):
            reason = "zero symbols"
        else:
            reason = f"an implausibly small symbol count ({last_result})"
        logger.info(
            "BSL index returned %s for %s files in %s; retrying after %.1fs",
            reason,
            expected_file_count,
            output_dir,
            delay,
        )
        await asyncio.sleep(delay)
        last_ok, last_result = build_index_with_fallback(
            output_dir,
            build_index=build_index,
            active_db=active_db,
        )
        if not last_ok:
            return last_ok, last_result
        if not _is_zero_symbol_summary(last_result) and not _is_implausibly_small_symbol_summary(
            last_result,
            expected_file_count=expected_file_count,
        ):
            return last_ok, last_result

    if _is_implausibly_small_symbol_summary(last_result, expected_file_count=expected_file_count):
        return (
            False,
            (
                "ERROR: Large BSL export is present, but indexing still returns an "
                "implausibly small symbol count after stabilization retries "
                f"({expected_file_count} files, last result: {last_result})."
            ),
        )

    return (
        False,
        (
            "ERROR: Large BSL export is present, but indexing still returns 0 symbols "
            f"after stabilization retries ({expected_file_count} files)."
        ),
    )


def build_index_with_fallback(
    output_dir: str,
    *,
    build_index: Callable[..., str],
    active_db: ActiveDbRef | None = None,
) -> tuple[bool, str]:
    """
    Build the BSL index from the most current path available.

    Host-side export writes directly into the host filesystem. After a dashboard
    workspace switch, the per-DB LSP container may still be remounting while the
    gateway can already see the new files under /hostfs-home. Prefer that local
    view first, then fall back to the LSP container mount.
    """
    attempts: list[tuple[str, str]] = []
    gateway_visible_path = _gateway_visible_host_path(output_dir)
    if gateway_visible_path not in {"/projects", "/workspace", "", None}:
        attempts.append((gateway_visible_path, ""))

    container = getattr(active_db, "lsp_container", "") if active_db else ""
    if container:
        attempts.append((_container_fallback_index_path(output_dir), container))
    else:
        attempts.append((output_dir, ""))

    seen: set[tuple[str, str]] = set()
    last_result = "ERROR: Unable to build BSL index."
    last_zero_summary: str | None = None
    for path, container_name in attempts:
        key = (path, container_name)
        if key in seen:
            continue
        seen.add(key)
        try:
            result = build_index(path, container=container_name)
        except Exception as exc:
            last_result = f"ERROR: {exc}"
            continue
        last_result = result
        summary = _summarize_index_result(result)
        if summary and _is_zero_symbol_summary(summary):
            last_zero_summary = summary
            continue
        if summary:
            return True, summary

    if last_zero_summary is not None:
        return True, last_zero_summary

    return False, last_result


async def run_designer_export(
    v8_path: Path,
    connection_args: list[str],
    output_dir: str,
    timeout: int | None,
    default_timeout: int,
    logger,
) -> tuple[int, str]:
    """Run 1cv8 DESIGNER /DumpConfigToFiles and return (returncode, log output)."""
    log_fd, log_path = tempfile.mkstemp(suffix=".log")
    os.close(log_fd)

    cmd = [str(v8_path), "DESIGNER"] + connection_args
    cmd += ["/DumpConfigToFiles", output_dir, "/DisableStartupDialogs", "/Out", log_path]

    env = {**os.environ, "LD_LIBRARY_PATH": "/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"}

    # NOTE: software licenses are NOT copied from the host into the container.
    # A 1C software license is bound to host hardware fingerprint.
    logger.warning(
        "Running 1cv8 DESIGNER inside container. If you use a 1C software "
        "(developer/community) license this path may invalidate it — "
        "configure EXPORT_HOST_URL to use the host service instead."
    )

    final_cmd = ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1024x768x24"] + cmd
    logger.info(f"Running: {v8_path.parent.name}/1cv8 DESIGNER → {output_dir}")

    proc = await asyncio.create_subprocess_exec(
        *final_cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    effective_timeout = timeout if timeout is not None else default_timeout
    await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)

    log_output = ""
    try:
        with open(log_path, encoding="utf-8-sig", errors="replace") as f:
            log_output = f.read().strip()
    except Exception:
        pass
    finally:
        try:
            os.unlink(log_path)
        except Exception:
            pass

    return proc.returncode, log_output


async def run_export_bsl(
    connection: str,
    output_dir: str,
    settings: SettingsLike,
    manager: ManagerLike,
    index_jobs: dict[str, dict],
    get_session_active: Callable[[], ActiveDbRef | None],
    get_connection_active: ConnectionDbResolver | None,
    build_index: Callable[[str, str], str],
    find_binaries: Callable[[], dict[str, Path]],
    pick_binary: Callable[[str], Path | None],
    run_designer_export_fn: Callable[[Path, list[str], str, int | None], Awaitable[tuple[int, str]]],
    logger,
    refresh_lsp_fn: Callable[[str, str], Awaitable[None]] | None = None,
) -> str:
    """Export BSL via host service or local 1cv8 DESIGNER and trigger indexing."""
    workspace_root = (settings.bsl_workspace or "").rstrip("/")
    unconfigured = not output_dir or output_dir.rstrip("/") in {
        "/projects",
        "/workspace",
        "/hostfs-home",
        workspace_root,
    }
    if unconfigured:
        gw_port = settings.port
        return (
            "ERROR: Папка выгрузки BSL не настроена.\n"
            f"Откройте дашборд: http://localhost:{gw_port}/dashboard#settings\n"
            "Вкладка «Настройки» → карточка «ПАПКА ВЫГРУЗКИ BSL» → укажите путь → Сохранить."
        )

    if settings.export_host_url:
        host_dir = output_dir
        if host_dir.startswith("/hostfs-home/"):
            host_dir = "/home/" + host_dir[len("/hostfs-home/") :]
        if settings.bsl_host_workspace and settings.bsl_workspace:
            container_ws = settings.bsl_workspace.rstrip("/")
            host_ws = settings.bsl_host_workspace.rstrip("/")
            if host_dir.startswith(container_ws):
                host_dir = host_ws + host_dir[len(container_ws) :]

        base_url = settings.export_host_url.rstrip("/")
        export_url = base_url + "/export-bsl"
        status_url = base_url + "/export-status"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    export_url,
                    json={"connection": connection, "output_dir": host_dir},
                )
                if resp.status_code == 409:
                    return (
                        "ERROR: Хост-сервис уже выполняет другую выгрузку. "
                        "Дождитесь завершения и повторите."
                    )
                data = resp.json()
                if not data.get("ok"):
                    return f"Export failed: {data.get('result', str(data))}"

            async with httpx.AsyncClient(timeout=15) as client:
                # Adaptive polling: fast at start (to surface host-side errors
                # like license / version mismatch quickly to the EPF UI), then
                # back off to 10s for long DESIGNER runs.
                for iteration in range(3600):
                    if iteration < 10:
                        await asyncio.sleep(1)
                    elif iteration < 30:
                        await asyncio.sleep(2)
                    else:
                        await asyncio.sleep(10)
                    try:
                        sr = await client.get(status_url, params={"connection": connection})
                        sd = sr.json()
                        status = sd.get("status", "")
                        active = get_session_active()
                        if active is None and get_connection_active is not None:
                            active = get_connection_active(connection)
                        if status == "done":
                            raw = sd.get("result", "").replace("\ufeff", "").strip()
                            expected_file_count = _extract_bsl_file_count(raw)
                            file_count = str(expected_file_count) if expected_file_count is not None else "?"
                            idx_msg = ""
                            index_jobs[connection] = {"status": "running", "result": ""}
                            # Refresh LSP container BEFORE indexing. Staging-swap
                            # rename changes the target dir's inode; any LSP
                            # container started earlier holds a stale bind-mount
                            # and grep sees an empty /projects. docker-control's
                            # start_lsp is idempotent — recreates the container
                            # only when the mount is stale or /projects is empty.
                            if refresh_lsp_fn is not None and active is not None:
                                try:
                                    await refresh_lsp_fn(
                                        getattr(active, "slug", "") or active.name,
                                        output_dir,
                                    )
                                except Exception as exc:
                                    logger.warning(
                                        f"LSP refresh before indexing failed: {exc}"
                                    )
                            try:
                                index_ok, index_result = await _finalize_index_result(
                                    output_dir=output_dir,
                                    build_index=build_index,
                                    active_db=active,
                                    logger=logger,
                                    expected_file_count=expected_file_count,
                                )
                                if index_ok:
                                    index_jobs[connection] = {
                                        "status": "done",
                                        "result": index_result,
                                    }
                                    idx_msg = f" Индекс: {index_result}."
                                else:
                                    index_jobs[connection] = {
                                        "status": "error",
                                        "result": index_result,
                                    }
                            except Exception as exc:
                                logger.warning(f"Auto-indexing BSL failed: {exc}")
                                index_jobs[connection] = {"status": "error", "result": str(exc)}
                            return f"Выгрузка завершена: {file_count} BSL файлов.{idx_msg}"
                        if status == "error":
                            raw_error = (sd.get("result", "") or "").replace("\ufeff", "").strip()
                            if "not authenticated" in raw_error.lower():
                                reused_result = await _reuse_existing_export_tree(
                                    connection=connection,
                                    output_dir=output_dir,
                                    build_index=build_index,
                                    active_db=active,
                                    index_jobs=index_jobs,
                                    logger=logger,
                                    existing_file_count=_existing_bsl_file_count(output_dir),
                                    fallback_reason="выгрузка через 1cv8 DESIGNER требует ПользовательBSL/ПарольBSL",
                                )
                                if not reused_result.startswith("ERROR:"):
                                    return reused_result
                                return _auth_hint_message(raw_error)
                            if _is_license_error(raw_error):
                                return await _reuse_existing_export_tree(
                                    connection=connection,
                                    output_dir=output_dir,
                                    build_index=build_index,
                                    active_db=active,
                                    index_jobs=index_jobs,
                                    logger=logger,
                                    existing_file_count=_existing_bsl_file_count(output_dir),
                                    fallback_reason="на хосте не найдена лицензия 1С для нового DumpConfigToFiles",
                                )
                            return f"Export failed: {raw_error}"
                    except Exception:
                        pass
            return "Export timed out after 2 hours"
        except Exception as exc:
            return f"ERROR calling export host service at {export_url}: {type(exc).__name__}: {exc}"

    if not settings.allow_container_designer_export:
        return (
            "ERROR: Экспорт через 1cv8 внутри контейнера отключён по соображениям "
            "безопасности лицензии.\n"
            "Настройте host-side export service и укажите EXPORT_HOST_URL в .env.\n"
            "Если вы осознанно используете HASP/CI, включите "
            "ALLOW_CONTAINER_DESIGNER_EXPORT=true."
        )

    available = find_binaries()
    if not available:
        base = Path("/opt/1cv8/x86_64")
        if base.exists():
            installed = ", ".join(d.name for d in base.iterdir() if d.is_dir()) or "(none)"
        else:
            installed = "(directory not found)"
        return (
            "ERROR: No 1cv8 thick client binary found under /opt/1cv8/x86_64/.\n"
            f"Installed versions: {installed}\n"
            "DESIGNER mode requires the full 1C platform (1cv8), not just "
            "the thin client (1cv8c) or server components.\n"
            "Install the full platform package: "
            "sudo apt install 1c-enterprise-8.3.XX.YYYY-common 1c-enterprise-8.3.XX.YYYY-client"
        )

    configured_ver = Path(settings.platform_path).name
    v8 = pick_binary(configured_ver)
    logger.info(
        f"Platform discovery: configured={configured_ver}, "
        f"available={list(available.keys())}, selected={v8}"
    )

    def parse_connection(conn: str) -> dict:
        result: dict = {}
        for part in conn.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                result[key.strip().lower()] = value.strip()
        return result

    parsed = parse_connection(connection)
    srvr = parsed.get("srvr", "")
    ref = parsed.get("ref", "")
    usr = parsed.get("usr", "")
    pwd = parsed.get("pwd", "")
    fpath = parsed.get("file", "")

    conn_args: list[str] = []
    if srvr and ref:
        conn_args += ["/S", f"{srvr}\\{ref}"]
    elif fpath:
        conn_args += ["/F", fpath]
    else:
        return f"ERROR: Cannot parse connection string: {connection}"
    if usr:
        conn_args += ["/N", usr]
    if pwd:
        conn_args += ["/P", pwd]

    out_path = Path(output_dir)
    existing_file_count_before_export = _existing_bsl_file_count(output_dir)
    if out_path.exists():
        import shutil as shutil_mod

        for child in out_path.iterdir():
            try:
                if child.is_dir():
                    shutil_mod.rmtree(child)
                else:
                    child.unlink()
            except Exception as exc:
                logger.warning(f"Cannot remove {child}: {exc}")
    out_path.mkdir(parents=True, exist_ok=True)

    export_timeout = settings.bsl_export_timeout
    if srvr and srvr.lower() not in ("localhost", "127.0.0.1", "::1"):
        export_timeout = max(export_timeout, 10800)

    try:
        rc, log_output = await run_designer_export_fn(v8, conn_args, output_dir, export_timeout)

        if rc != 0:
            vm = re.search(r"([\d.]+) - ([\d.]+)\)", log_output)
            if vm:
                server_ver = vm.group(2)
                if server_ver in available and available[server_ver] != v8:
                    alt_v8 = available[server_ver]
                    logger.info(
                        f"Version mismatch: client={vm.group(1)}, server={server_ver}. "
                        f"Retrying with {alt_v8}"
                    )
                    rc, log_output = await run_designer_export_fn(
                        alt_v8,
                        conn_args,
                        output_dir,
                        export_timeout,
                    )
                elif server_ver not in available:
                    installed = ", ".join(sorted(available.keys()))
                    return (
                        "Export failed: version mismatch.\n"
                        f"Server version: {server_ver}\n"
                        f"Installed 1cv8 versions: {installed}\n"
                        "Install the matching platform: sudo apt install "
                        f"1c-enterprise-{server_ver}-common 1c-enterprise-{server_ver}-client"
                    )

        if rc == 0:
            bsl_count = sum(1 for _ in out_path.rglob("*.bsl"))
            result = f"Export completed successfully.\nBSL files in {output_dir}: {bsl_count}"
            if log_output:
                result += f"\n\nLog:\n{log_output}"

            if manager.has_tool("did_change_watched_files"):
                try:
                    await manager.call_tool("did_change_watched_files", {"language": "bsl", "changes_json": "[]"})
                except Exception:
                    pass

            index_jobs[connection] = {"status": "running", "result": ""}
            try:
                active = get_session_active()
                if active is None and get_connection_active is not None:
                    active = get_connection_active(connection)
                index_ok, index_result = await _finalize_index_result(
                    output_dir=output_dir,
                    build_index=build_index,
                    active_db=active,
                    logger=logger,
                    expected_file_count=bsl_count,
                )
                if index_ok:
                    index_jobs[connection] = {"status": "done", "result": index_result}
                    result += f" Индекс: {index_result}."
                else:
                    index_jobs[connection] = {"status": "error", "result": index_result}
            except Exception as exc:
                logger.warning(f"Auto-indexing BSL failed: {exc}")
                index_jobs[connection] = {"status": "error", "result": str(exc)}

            m_files = re.search(r"(\d+)\s+BSL files", result)
            file_count = m_files.group(1) if m_files else "?"
            suffix = result[result.find(" Индекс:") :] if " Индекс:" in result else ""
            return f"Выгрузка завершена: {file_count} BSL файлов.{suffix}"

        if "License not found" in log_output or "license" in log_output.lower():
            active = get_session_active()
            if active is None and get_connection_active is not None:
                active = get_connection_active(connection)
            reused_result = await _reuse_existing_export_tree(
                connection=connection,
                output_dir=output_dir,
                build_index=build_index,
                active_db=active,
                index_jobs=index_jobs,
                logger=logger,
                existing_file_count=existing_file_count_before_export,
                fallback_reason="внутри контейнера не найдена лицензия 1С",
            )
            if not reused_result.startswith("ERROR:"):
                return reused_result
            return (
                "Export failed: лицензия 1С не найдена внутри контейнера.\n\n"
                "Проверьте:\n"
                "1. Файл лицензии (.lic) должен быть в /var/1C/licenses/ или /opt/1cv8/conf/ на хосте\n"
                "2. В docker-compose.yml должен быть маунт: /var/1C:/var/1C:ro\n"
                "3. После изменений: docker compose up -d gateway\n\n"
                f"Лог 1cv8:\n{log_output}"
            )

        if rc == 139:
            ver = v8.parent.name if v8 else "?"
            return (
                f"Export failed: 1cv8 {ver} завершился аварийно (Segmentation fault).\n\n"
                "Вероятная причина: неполная установка платформы.\n"
                "Убедитесь, что установлен пакет common:\n"
                f"  sudo dpkg -i 1c-enterprise-{ver}-common_*.deb\n"
                f"  sudo dpkg -i 1c-enterprise-{ver}-client_*.deb\n\n"
                f"Проверка: dpkg -l | grep 1c-enterprise | grep {ver}"
            )

        raw_error = f"Export failed (rc={rc}):\n{log_output}"
        if "not authenticated" in log_output.lower():
            if existing_file_count_before_export > 0:
                active = get_session_active()
                if active is None and get_connection_active is not None:
                    active = get_connection_active(connection)
                return await _reuse_existing_export_tree(
                    connection=connection,
                    output_dir=output_dir,
                    build_index=build_index,
                    active_db=active,
                    index_jobs=index_jobs,
                    logger=logger,
                    existing_file_count=existing_file_count_before_export,
                )
            return _auth_hint_message(raw_error)

        return raw_error

    except asyncio.TimeoutError:
        mins = export_timeout // 60
        return f"ERROR: 1cv8 DESIGNER timed out after {mins} minutes"
    except Exception as exc:
        return f"ERROR: {exc}"
