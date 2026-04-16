#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_HWPX_ROOT="$(cd "$STACK_ROOT/../.." && pwd)"
PROJECTS_ROOT="$(cd "$PYTHON_HWPX_ROOT/.." && pwd)"
MCP_ROOT="${HWPX_STACK_MCP_ROOT:-$PROJECTS_ROOT/hwpx-mcp-server}"
MCP_EDITABLE="${MCP_ROOT}[test]"
SKILL_ROOT="${HWPX_STACK_SKILL_ROOT:-$PROJECTS_ROOT/hwpx-skill}"
VENV_DIR="${HWPX_STACK_VENV:-$STACK_ROOT/.venv-compat311}"
if [[ -n "${HWPX_STACK_PYTHON:-}" ]]; then
  PYTHON_BIN="$HWPX_STACK_PYTHON"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.11)"
else
  PYTHON_BIN="$(command -v python3)"
fi
WORK_DIR="$STACK_ROOT/tmp/smoke"
FIXTURE_ROOT="$STACK_ROOT/fixtures"
FIXTURE_MATRIX="$FIXTURE_ROOT/fixture_matrix.json"
FIXTURE_DOC="$FIXTURE_ROOT/core/00_smoke_min.hwpx"
CORE_DOC="$WORK_DIR/core_created.hwpx"
REPLACED_DOC="$WORK_DIR/core_replaced.hwpx"
FIXTURE_EXTRACT_OUT="$WORK_DIR/fixture_extract.txt"
EXTRACT_OUT="$WORK_DIR/skill_extract.txt"
INSPECT_OUT="$WORK_DIR/skill_inspect.txt"
LOG_PATH="$WORK_DIR/stack_smoke.log"

mkdir -p "$WORK_DIR"
: > "$LOG_PATH"

log() {
  echo "$@" | tee -a "$LOG_PATH"
}

log "[START] HWPX stack smoke test"
log "[WORK_DIR] $WORK_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  log "[SETUP] creating venv at $VENV_DIR"
  uv venv "$VENV_DIR" --python "$PYTHON_BIN" | tee -a "$LOG_PATH"
fi

log "[SETUP] syncing editable installs"
uv pip install --python "$VENV_DIR/bin/python" -e "$PYTHON_HWPX_ROOT" -e "$MCP_EDITABLE" | tee -a "$LOG_PATH"

log "[FIXTURE] editor-authored fixture smoke matrix"
"$VENV_DIR/bin/python" "$STACK_ROOT/scripts/fixture_smoke_matrix.py" --fixture-root "$FIXTURE_ROOT" --matrix "$FIXTURE_MATRIX" | tee -a "$LOG_PATH"

log "[FIXTURE] skill text extract smoke on editor-authored baseline"
"$VENV_DIR/bin/python" "$SKILL_ROOT/scripts/text_extract.py" "$FIXTURE_DOC" | tee "$FIXTURE_EXTRACT_OUT" | tee -a "$LOG_PATH"
grep -q 'SMOKE_01' "$FIXTURE_EXTRACT_OUT"

log "[CORE] python-hwpx create/open/save smoke"
"$VENV_DIR/bin/python" "$STACK_ROOT/scripts/core_stack_smoke.py" "$CORE_DOC" | tee -a "$LOG_PATH"

log "[MCP] focused contract + end-to-end smoke"
(
  cd "$MCP_ROOT"
  "$VENV_DIR/bin/python" -m pytest -q tests/test_contract.py tests/test_mcp_end_to_end.py
) | tee -a "$LOG_PATH"

log "[SKILL] text extract smoke"
"$VENV_DIR/bin/python" "$SKILL_ROOT/scripts/text_extract.py" "$CORE_DOC" | tee "$EXTRACT_OUT" | tee -a "$LOG_PATH"

log "[SKILL] replace + namespace normalize smoke"
"$VENV_DIR/bin/python" "$SKILL_ROOT/examples/03_template_replace.py" "$CORE_DOC" "$REPLACED_DOC" --replace '기준선=스모크테스트' | tee -a "$LOG_PATH"

log "[SKILL] inspect replaced output"
"$VENV_DIR/bin/python" "$SKILL_ROOT/examples/02_extract_and_inspect.py" "$REPLACED_DOC" | tee "$INSPECT_OUT" | tee -a "$LOG_PATH"

grep -q '스모크테스트' "$INSPECT_OUT"

log "[DONE] stack smoke test passed"
log "[LOG] $LOG_PATH"
