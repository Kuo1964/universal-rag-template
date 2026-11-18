#!/usr/bin/env bash
# 跨平台、無硬編碼路徑的 MCP 伺服器啟動器（供 IBM Bob / Antigravity / Claude Desktop 呼叫）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
elif [ -x "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON_BIN}" "${PROJECT_ROOT}/mcp_server.py"
