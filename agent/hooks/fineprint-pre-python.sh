#!/usr/bin/env bash
# PreToolUse-style hook: run `fineprint check` before a shell command that runs Python.
#
# Input: the hook JSON on stdin, with the shell command at .tool_input.command
# (the common shape for PreToolUse hooks). Output: exit 0 lets the command run,
# exit 2 blocks it and the text on stderr goes back to your coding agent.
#
# Environment:
#   FINEPRINT_HOOK_PATH    directory to scan (default: the hook's working directory)
#   FINEPRINT_HOOK_STRICT  set to 1 to also block on CONDITIONS (not only BLOCK)
#   FINEPRINT_USE          commercial (default) or noncommercial
#   FINEPRINT_FAIL_CLOSED  set to 1 to block when the check cannot run (API down,
#                          fineprint missing or crashing); default is to warn and let it run
#   FINEPRINT_BIN          fineprint executable (default: fineprint on PATH)
#   FINEPRINT_API          FinePrint API base URL (default http://localhost:8000)
set -u

closed() {
  case "$(printf '%s' "${FINEPRINT_FAIL_CLOSED:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

# Exit for "the check could not run": block when fail-closed, else warn and allow.
unchecked() {
  if closed; then
    echo "fineprint hook: $1; blocking because FINEPRINT_FAIL_CLOSED is set." >&2
    exit 2
  fi
  echo "fineprint hook: WARNING: $1; command allowed unchecked. Set FINEPRINT_FAIL_CLOSED=1 to block instead." >&2
  exit 0
}

input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")' 2>/dev/null)"

# Only act on commands that run Python code.
if ! printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])(python[0-9.]*|uv run|poetry run|pytest|jupyter|accelerate launch|torchrun)([[:space:]]|$)'; then
  exit 0
fi

bin="${FINEPRINT_BIN:-fineprint}"
if ! command -v "$bin" >/dev/null 2>&1; then
  unchecked "'$bin' not found, models not checked"
fi

args=(check "${FINEPRINT_HOOK_PATH:-.}")
[ "${FINEPRINT_HOOK_STRICT:-0}" = "1" ] && args+=(--strict)

out="$("$bin" "${args[@]}" 2>&1)"
code=$?

case "$code" in
  0) exit 0 ;;
  1|2)
    {
      echo "FinePrint stopped this command for ${FINEPRINT_USE:-commercial} use: a model in this repo is BLOCK, could not be checked with fail-closed on, or is CONDITIONS in strict mode."
      echo
      echo "$out"
      echo
      echo "Review with 'fineprint report MODEL_ID', switch to a model marked ALLOW, or set FINEPRINT_ALLOW=org/name."
    } >&2
    exit 2 ;;
  3) unchecked "FinePrint API not reachable, models not checked" ;;
  *) unchecked "fineprint exited $code, models not checked" ;;
esac
