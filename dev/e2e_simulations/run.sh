#!/usr/bin/env bash

set -euo pipefail

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${E2E_DIR}/.venv"
REQ_FILE="${E2E_DIR}/requirements.txt"
BASE_URL="${E2E_BASE_URL:-http://localhost:8000}"
PY_BIN="${E2E_PYTHON_BIN:-python3}"
if [ -z "${E2E_PYTHON_BIN:-}" ] && command -v python3.12 >/dev/null 2>&1; then
  PY_BIN="python3.12"
fi
if [ -z "${E2E_PYTHON_BIN:-}" ] && [ "${PY_BIN}" = "python3" ] && command -v pyenv >/dev/null 2>&1; then
  if pyenv install -s 3.12.9 >/dev/null 2>&1; then
    PY_BIN="$(pyenv prefix 3.12.9)/bin/python"
  fi
fi
HEADED=0
SLOW_MO_MS=""
PYTEST_ARGS=()

export LD_LIBRARY_PATH="/run/current-system/sw/lib:/run/current-system/sw/share/nix-ld/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

for arg in "$@"; do
  if [ "${arg}" = "--headed" ]; then
    HEADED=1
  elif [ "${arg}" = "--slow" ]; then
    SLOW_MO_MS="${E2E_SLOW_MO_MS:-250}"
  elif [[ "${arg}" == --slow=* ]]; then
    SLOW_MO_MS="${arg#--slow=}"
  elif [[ "${arg}" == --slow-ms=* ]]; then
    SLOW_MO_MS="${arg#--slow-ms=}"
  else
    PYTEST_ARGS+=("${arg}")
  fi
done

if [ -n "${SLOW_MO_MS}" ] && ! [[ "${SLOW_MO_MS}" =~ ^[0-9]+$ ]]; then
  echo "Invalid slow mode value: '${SLOW_MO_MS}'. Use --slow or --slow=<milliseconds>."
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  "${PY_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "${REQ_FILE}"
python -m playwright install chromium

if ! python - <<'PY'
import greenlet  # noqa: F401
PY
then
  echo "Playwright runtime dependency missing: libstdc++.so.6"
  echo "Install it on host (example: sudo apt-get install libstdc++6) and re-run."
  exit 1
fi

export E2E_BASE_URL="${BASE_URL}"
if [ -n "${SLOW_MO_MS}" ]; then
  export E2E_SLOW_MO_MS="${SLOW_MO_MS}"
fi
cd "${E2E_DIR}"
if [ "${HEADED}" = "1" ]; then
  python -m pytest -q --headed tests "${PYTEST_ARGS[@]}"
else
  python -m pytest -q tests "${PYTEST_ARGS[@]}"
fi
