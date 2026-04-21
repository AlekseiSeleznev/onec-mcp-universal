#!/bin/sh
set -eu

mkdir -p /data
chown -R app:app /data 2>/dev/null || true

exec gosu app python -m gateway
