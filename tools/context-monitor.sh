#!/usr/bin/env bash
set -euo pipefail

MAX_TOKENS="${MAX_TOKENS:-200000}"
WARN_PERCENT="${WARN_PERCENT:-70}"
CRITICAL_PERCENT="${CRITICAL_PERCENT:-85}"

input_text="$(cat)"
delta=$(( ${#input_text} / 4 ))

raw_tokens="${ONEC_CONTEXT_TOKENS:-0}"
if [[ "$raw_tokens" =~ ^-?[0-9]+$ ]]; then
  current="$raw_tokens"
else
  current=0
fi
current=$(( current + delta ))
export ONEC_CONTEXT_TOKENS="$current"

pct=$(( current * 100 / MAX_TOKENS ))
if (( pct >= CRITICAL_PERCENT )); then
  echo "!! Context ${pct}% (${current} tokens). Save session now: /session-save" >&2
elif (( pct >= WARN_PERCENT )); then
  echo "! Context ${pct}% (${current} tokens). Consider /session-save" >&2
fi

printf '%s' "$input_text"
