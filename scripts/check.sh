#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
require_frontend
require_venv
cd "$PROJECT_ROOT/frontend"
"$FRONTEND_PM" run build
cd "$PROJECT_ROOT/backend"
"$PROJECT_ROOT/.venv/bin/python" -m compileall -q app
"$PROJECT_ROOT/.venv/bin/python" -m pytest -q
echo "前端类型检查、构建、后端语法检查及自动测试通过。"
