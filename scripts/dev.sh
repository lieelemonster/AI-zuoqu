#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
case "${1:-}" in
  api)
    require_venv
    cd "$PROJECT_ROOT/backend"
    exec "$PROJECT_ROOT/.venv/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    ;;
  web)
    require_frontend
    cd "$PROJECT_ROOT/frontend"
    exec "$FRONTEND_PM" run dev
    ;;
  worker)
    require_venv
    cd "$PROJECT_ROOT/backend"
    exec "$PROJECT_ROOT/.venv/bin/python" -m app.worker
    ;;
  env-check)
    require_venv
    cd "$PROJECT_ROOT/backend"
    exec "$PROJECT_ROOT/.venv/bin/python" -m app.rendering.environment
    ;;
  *)
    echo "用法：bash scripts/dev.sh {api|web|worker|env-check}" >&2
    exit 1
    ;;
esac
