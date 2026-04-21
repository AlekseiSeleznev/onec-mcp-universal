"""Coverage for gateway.__main__ entrypoint."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_main_runs_uvicorn_with_settings():
    from gateway.config import settings

    with patch("uvicorn.run") as run:
        runpy.run_module("gateway.__main__", run_name="__main__")

    run.assert_called_once_with(
        "gateway.server:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


def test_importing_entrypoint_does_not_run_uvicorn():
    with patch("uvicorn.run") as run:
        runpy.run_module("gateway.__main__", run_name="gateway.__main__")

    run.assert_not_called()
