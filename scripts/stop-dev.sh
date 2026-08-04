#!/usr/bin/env bash
# Stops only processes started by scripts/run-dev.sh from this checkout.

set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
runtime_root="$project_root/.runtime"

project_process() {
  local process_id="$1"
  local command_line

  command_line="$(ps -p "$process_id" -o command= 2>/dev/null || true)"
  [[ "$command_line" == *"$project_root"* ]]
}

stop_process_tree() {
  local process_id="$1"
  local child_id

  while IFS= read -r child_id; do
    [[ -n "$child_id" ]] && stop_process_tree "$child_id"
  done < <(pgrep -P "$process_id" 2>/dev/null || true)

  kill -TERM "$process_id" 2>/dev/null || true
}

for name in backend worker frontend; do
  pid_path="$runtime_root/$name.pid"
  [[ -f "$pid_path" ]] || continue

  process_id="$(tr -d '[:space:]' < "$pid_path")"
  if [[ ! "$process_id" =~ ^[1-9][0-9]*$ ]]; then
    printf 'Removed invalid %s PID file.\n' "$name" >&2
  elif ! kill -0 "$process_id" 2>/dev/null; then
    printf 'Removed stale %s PID file.\n' "$name"
  elif project_process "$process_id"; then
    stop_process_tree "$process_id"
    printf 'Stopped %s (PID %s).\n' "$name" "$process_id"
  else
    printf 'Skipped PID %s for %s because it no longer belongs to this checkout.\n' "$process_id" "$name" >&2
  fi

  rm -f "$pid_path"
done
