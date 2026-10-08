#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
require_frontend
if [ -z "$PYTHON_BIN" ]; then
  echo "需要 Python 3.10+（建议 3.12）。" >&2
  exit 1
fi
cd "$PROJECT_ROOT"
export PIP_CACHE_DIR="$PROJECT_ROOT/work/pip-cache"
if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
require_venv
if [ -f backend/requirements.lock.txt ]; then
  .venv/bin/python -m pip install -r backend/requirements.lock.txt
else
  .venv/bin/python -m pip install -r backend/requirements.txt
  .venv/bin/python -m pip freeze > backend/requirements.lock.txt
fi
if [ ! -f .env ]; then
  cp .env.example .env
fi
cd "$PROJECT_ROOT/frontend"
FRONTEND_REGISTRY="${NPM_REGISTRY:-https://registry.npmjs.org}"
echo "前端依赖下载地址：$FRONTEND_REGISTRY"
if [[ "$FRONTEND_PM" == *pnpm ]]; then
  if [ -f pnpm-lock.yaml ]; then
    "$FRONTEND_PM" install --frozen-lockfile --store-dir "$PROJECT_ROOT/work/pnpm-store" --registry "$FRONTEND_REGISTRY" --network-concurrency 1 --fetch-retry-mintimeout 2000 --fetch-retry-maxtimeout 5000 --fetch-timeout 30000
  else
    "$FRONTEND_PM" install --store-dir "$PROJECT_ROOT/work/pnpm-store" --registry "$FRONTEND_REGISTRY" --network-concurrency 1 --fetch-retry-mintimeout 2000 --fetch-retry-maxtimeout 5000 --fetch-timeout 30000
  fi
else
  if [ -f package-lock.json ]; then
    "$FRONTEND_PM" ci --cache "$PROJECT_ROOT/work/npm-cache" --registry "$FRONTEND_REGISTRY"
  else
    "$FRONTEND_PM" install --cache "$PROJECT_ROOT/work/npm-cache" --registry "$FRONTEND_REGISTRY"
  fi
fi
echo "依赖安装完成。分别运行 bash scripts/dev.sh api 和 bash scripts/dev.sh web。"
