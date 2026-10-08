#!/usr/bin/env bash
# 由其他脚本 source；只修改当前脚本进程的 PATH。
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLED_RUNTIME="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies"

if ! command -v node >/dev/null 2>&1 && [ -x "$BUNDLED_RUNTIME/node/bin/node" ]; then
  export PATH="$BUNDLED_RUNTIME/node/bin:$PATH"
fi
if command -v pnpm >/dev/null 2>&1; then
  FRONTEND_PM="$(command -v pnpm)"
elif command -v npm >/dev/null 2>&1; then
  FRONTEND_PM="$(command -v npm)"
elif [ -x "$BUNDLED_RUNTIME/bin/fallback/pnpm" ]; then
  FRONTEND_PM="$BUNDLED_RUNTIME/bin/fallback/pnpm"
else
  FRONTEND_PM=""
fi

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3 python "$BUNDLED_RUNTIME/python/bin/python3"; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    PYTHON_BIN="$(command -v "$candidate")"
    break
  fi
done

require_frontend() {
  if ! command -v node >/dev/null 2>&1 || [ -z "$FRONTEND_PM" ]; then
    echo "需要 Node.js 22.12+ 和 npm 或 pnpm。" >&2
    exit 1
  fi
  node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22||(a===22&&b<12)){console.error("需要 Node.js 22.12+");process.exit(1)}'
}

require_venv() {
  if [ ! -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    echo "请先运行 bash scripts/setup.sh。" >&2
    exit 1
  fi
}
