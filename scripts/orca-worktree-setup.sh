#!/usr/bin/env bash
set -euo pipefail
ROOT="${ORCA_ROOT_PATH:-}"
WT="${ORCA_WORKTREE_PATH:-$PWD}"
if [ -z "$ROOT" ]; then
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$WT"
if [ -f "$ROOT/.mcp.json" ]; then
  cp -f "$ROOT/.mcp.json" "$WT/.mcp.json"
fi
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
