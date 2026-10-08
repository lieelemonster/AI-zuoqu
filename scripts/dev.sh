#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

run_backend_module() {
  require_venv
  cd "$PROJECT_ROOT/backend"
  exec "$PROJECT_ROOT/.venv/bin/python" -m "$@"
}

case "${1:-}" in
  api)
    run_backend_module uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    ;;
  web)
    require_frontend
    cd "$PROJECT_ROOT/frontend"
    exec "$FRONTEND_PM" run dev
    ;;
  worker) run_backend_module app.worker ;;
  env-check) run_backend_module app.rendering.environment ;;
  check-schemas) run_backend_module app.schemas.check ;;
  check-presets) run_backend_module app.presets ;;
  check-midi) run_backend_module app.rendering.check_midi ;;
  check-render) run_backend_module app.rendering.check_render ;;
  check-encode) run_backend_module app.rendering.check_encode ;;
  check-lyrics) run_backend_module app.lyrics.check ;;
  check-arrangement) run_backend_module app.composer.check_arrangement ;;
  check-melody) run_backend_module app.composer.check_melody ;;
  check-demo) run_backend_module app.composer.check_demo ;;
  check-model) run_backend_module app.providers.check ;;
  test)
    shift
    run_backend_module pytest -q "$@"
    ;;
  *)
    echo "用法：bash scripts/dev.sh {api|web|worker|env-check|check-schemas|check-presets|check-midi|check-render|check-encode|check-lyrics|check-arrangement|check-melody|check-demo|check-model|test}" >&2
    exit 1
    ;;
esac
