"""
All-in-one process manager for onec-mcp-universal.
Starts and monitors all sub-services, then runs the MCP gateway in foreground.
"""

import logging
import os
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("entrypoint")

BSL_WORKSPACE = os.environ.get("BSL_WORKSPACE", "/projects")
PLATFORM_PATH = os.environ.get("PLATFORM_PATH", "/opt/1cv8/x86_64/8.3.27.2074")
BSL_JAVA_XMX = os.environ.get("BSL_JAVA_XMX", "4g")
BSL_JAVA_XMS = os.environ.get("BSL_JAVA_XMS", "1g")
ONEC_TIMEOUT = os.environ.get("ONEC_TIMEOUT", "180")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
ENABLED_BACKENDS = os.environ.get("ENABLED_BACKENDS", "onec-toolkit,platform-context,bsl-lsp-bridge")


@dataclass
class Service:
    name: str
    cmd: list[str]
    env: dict = field(default_factory=dict)
    health_url: str = ""
    health_retries: int = 30
    health_interval: float = 2.0
    proc: subprocess.Popen | None = field(default=None, repr=False)


def _env(**extra) -> dict:
    e = os.environ.copy()
    e.update(extra)
    return e


SERVICES: list[Service] = [
    Service(
        name="onec-toolkit",
        cmd=[sys.executable, "-m", "onec_mcp_toolkit_proxy"],
        env=_env(PORT="6003", TIMEOUT=ONEC_TIMEOUT, RESPONSE_FORMAT="json",
                 ALLOW_DANGEROUS_WITH_APPROVAL="true"),
        health_url="http://localhost:6003/health",
    ),
    Service(
        name="bsl-session-manager",
        cmd=[
            "/usr/bin/lsp-session-manager",
            "--port=9999",
            f"--workspace={BSL_WORKSPACE}",
            "--command=java",
            "--",
            f"-Xmx{BSL_JAVA_XMX}", f"-Xms{BSL_JAVA_XMS}",
            "-XX:+UseG1GC", "-XX:MaxGCPauseMillis=200",
            "-jar", "/opt/bsl-ls/bsl-language-server.jar",
            "lsp", "-c", "/etc/mcp-lsp-bridge/bsl-ls.json",
        ],
        health_retries=60,   # BSL LS takes ~30-60s to start
    ),
    Service(
        name="platform-context",
        cmd=[
            "java", "-jar", "/opt/platform/mcp-bsl-context.jar",
            "--mode", "sse",
            "--platform-path", PLATFORM_PATH,
            "--port", "8081",
        ],
        health_url="http://localhost:8081/sse",
        health_retries=40,
        health_interval=3.0,
    ),
]


def _wait_http(url: str, retries: int, interval: float) -> bool:
    for i in range(retries):
        try:
            urllib.request.urlopen(url, timeout=3)
            return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _is_alive(svc: Service) -> bool:
    return svc.proc is not None and svc.proc.poll() is None


def start_service(svc: Service) -> None:
    log.info(f"[{svc.name}] starting: {' '.join(svc.cmd[:3])}...")
    svc.proc = subprocess.Popen(
        svc.cmd,
        env=svc.env if svc.env else None,
        cwd="/app" if svc.name == "onec-toolkit" else None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if svc.health_url:
        ok = _wait_http(svc.health_url, svc.health_retries, svc.health_interval)
        if ok:
            log.info(f"[{svc.name}] ready (pid={svc.proc.pid})")
        else:
            log.warning(f"[{svc.name}] health check timed out — continuing anyway")
    else:
        # no health URL: just wait a bit
        time.sleep(2)
        if _is_alive(svc):
            log.info(f"[{svc.name}] started (pid={svc.proc.pid})")
        else:
            log.error(f"[{svc.name}] exited immediately (rc={svc.proc.returncode})")


def stop_all(services: list[Service]) -> None:
    for svc in reversed(services):
        if _is_alive(svc):
            log.info(f"[{svc.name}] terminating...")
            svc.proc.terminate()
    for svc in reversed(services):
        if svc.proc:
            try:
                svc.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                svc.proc.kill()


def main() -> None:
    enabled = {s.strip() for s in ENABLED_BACKENDS.split(",")}
    services_to_start = [s for s in SERVICES if s.name.split("-")[0] == "bsl" or s.name in enabled
                         or s.name == "bsl-session-manager"]
    # always start bsl-session-manager if bsl-lsp-bridge backend is enabled
    if "bsl-lsp-bridge" not in enabled:
        services_to_start = [s for s in services_to_start if s.name != "bsl-session-manager"]

    shutdown = [False]

    def _sighandler(sig, frame):
        log.info("Shutdown signal received")
        shutdown[0] = True

    signal.signal(signal.SIGTERM, _sighandler)
    signal.signal(signal.SIGINT, _sighandler)

    for svc in services_to_start:
        start_service(svc)

    # Build gateway environment
    gateway_env = _env(
        ONEC_TOOLKIT_URL="http://localhost:6003/mcp",
        PLATFORM_CONTEXT_URL="http://localhost:8081/sse",
        BSL_LSP_COMMAND="/usr/bin/mcp-lsp-bridge",
        LOG_LEVEL=LOG_LEVEL,
        ENABLED_BACKENDS=ENABLED_BACKENDS,
        PORT="8080",
    )

    log.info("Starting MCP gateway on :8080...")
    gateway = subprocess.Popen(
        [sys.executable, "-m", "gateway"],
        cwd="/opt/gateway",
        env=gateway_env,
    )

    # Monitor loop
    while not shutdown[0]:
        if gateway.poll() is not None:
            log.error(f"Gateway exited (rc={gateway.returncode}), shutting down")
            break
        for svc in services_to_start:
            if not _is_alive(svc):
                log.warning(f"[{svc.name}] died (rc={svc.proc.returncode}), restarting...")
                start_service(svc)
        time.sleep(5)

    gateway.terminate()
    try:
        gateway.wait(timeout=10)
    except subprocess.TimeoutExpired:
        gateway.kill()

    stop_all(services_to_start)
    sys.exit(0)


if __name__ == "__main__":
    main()
