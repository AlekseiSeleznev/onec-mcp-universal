#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${GATEWAY_DIR}"

if ! python3 -c "import pytest_asyncio" >/dev/null 2>&1; then
  echo "ERROR: missing dependency 'pytest-asyncio'." >&2
  echo "Install dev dependencies first:" >&2
  echo "  python3 -m venv ../.venv" >&2
  echo "  ../.venv/bin/pip install -r requirements-dev.txt" >&2
  exit 2
fi

if ! python3 -c "import pytest" >/dev/null 2>&1; then
  echo "ERROR: missing dependency 'pytest'." >&2
  echo "Install dev dependencies first:" >&2
  echo "  python3 -m venv ../.venv" >&2
  echo "  ../.venv/bin/pip install -r requirements-dev.txt" >&2
  exit 2
fi

if [ "$#" -eq 0 ]; then
  set -- -q --cov=gateway --cov-branch --cov-report=term-missing --cov-fail-under=94
fi

exec python3 -m pytest tests "$@"
