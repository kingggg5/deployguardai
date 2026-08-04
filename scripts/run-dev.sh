#!/usr/bin/env bash
# Starts a local, connected-mode DeployGuard development runtime on Unix-like hosts.
# Synthetic records are never seeded by this helper. Use `make demo` for the
# intentionally isolated and visibly-labelled synthetic experience.

set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
backend_root="$project_root/backend"
frontend_root="$project_root/frontend"
runtime_root="$project_root/.runtime"
venv_root="$backend_root/.venv"
python_command="${PYTHON_BIN:-python3}"
skip_install=false

usage() {
  printf 'Usage: %s [--skip-install]\n' "${0##*/}"
}

while (($# > 0)); do
  case "$1" in
    --skip-install)
      skip_install=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  shift
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Required command not found: %s\n' "$1" >&2
    exit 1
  fi
}

require_command "$python_command"
require_command node
require_command npm

mkdir -p "$runtime_root"

for name in backend worker frontend; do
  pid_path="$runtime_root/$name.pid"
  [[ -f "$pid_path" ]] || continue

  process_id="$(tr -d '[:space:]' < "$pid_path")"
  if [[ "$process_id" =~ ^[1-9][0-9]*$ ]] && kill -0 "$process_id" 2>/dev/null; then
    command_line="$(ps -p "$process_id" -o command= 2>/dev/null || true)"
    if [[ "$command_line" == *"$project_root"* ]]; then
      printf 'DeployGuard %s is already running (PID %s). Run scripts/stop-dev.sh first.\n' "$name" "$process_id" >&2
      exit 1
    fi
  fi

  rm -f "$pid_path"
done

if [[ ! -x "$venv_root/bin/python" ]]; then
  "$python_command" -m venv "$venv_root"
fi

python_exe="$venv_root/bin/python"
angular_cli="$frontend_root/node_modules/@angular/cli/bin/ng.js"

# A source run is always connected mode. Reuse an explicitly supplied database
# URL, otherwise isolate its empty local database under .runtime so legacy
# backend/deployguard.db fixtures cannot appear as real data.
if [[ -z "${DATABASE_URL:-}" ]]; then
  local_database_path="$($python_exe - "$runtime_root" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve().as_posix())
PY
)"
  export DATABASE_URL="sqlite:///$local_database_path"
fi
export SEED_SYNTHETIC_DATA=false

if [[ "$skip_install" == false ]]; then
  "$python_exe" -m pip install --disable-pip-version-check -r "$backend_root/requirements.txt"
  if [[ ! -d "$frontend_root/node_modules" ]]; then
    npm --prefix "$frontend_root" ci
  fi
fi

if [[ ! -f "$angular_cli" ]]; then
  printf 'Angular CLI is not installed. Run without --skip-install or run npm ci in frontend/.\n' >&2
  exit 1
fi

start_process() {
  local name="$1"
  local working_directory="$2"
  shift 2

  (
    cd "$working_directory"
    exec nohup "$@"
  ) >"$runtime_root/$name.stdout.log" 2>"$runtime_root/$name.stderr.log" < /dev/null &
  printf '%s\n' "$!" > "$runtime_root/$name.pid"
}

api_is_ready() {
  "$python_exe" - <<'PY'
from urllib.error import URLError
from urllib.request import urlopen

try:
    with urlopen("http://127.0.0.1:8100/api/v1/health/ready", timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except (OSError, URLError):
    raise SystemExit(1)
PY
}

start_process backend \
  "$backend_root" \
  "$python_exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload

api_ready=false
for _attempt in {1..60}; do
  if api_is_ready; then
    api_ready=true
    break
  fi
  sleep 0.5
done

if [[ "$api_ready" == false ]]; then
  printf 'DeployGuard API did not become ready. Inspect %s\n' "$runtime_root/backend.stderr.log" >&2
  "$project_root/scripts/stop-dev.sh" || true
  exit 1
fi

start_process worker \
  "$backend_root" \
  "$python_exe" -m app.worker --poll-interval 1 --lease-timeout 300
start_process frontend \
  "$frontend_root" \
  "$(command -v node)" "$angular_cli" serve --host 127.0.0.1 --port 4300

printf 'DeployGuard API: http://127.0.0.1:8100/docs\n'
printf 'DeployGuard UI:  http://127.0.0.1:4300\n'
printf 'Mode:            connected (synthetic seeding disabled)\n'
printf 'Worker:          PID %s\n' "$(<"$runtime_root/worker.pid")"
printf 'Logs:            %s\n' "$runtime_root"
