#!/usr/bin/env bash
set -euo pipefail

fail=0

need() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Falta: $cmd" >&2
    fail=1
  fi
}

need python3

python3 - <<'PY'
import sys
ok = sys.version_info >= (3,10)
print(f"python3: {sys.version.split()[0]} (ok={ok})")
raise SystemExit(0 if ok else 1)
PY
if [ $? -ne 0 ]; then
  echo "Requiere Python 3.10+" >&2
  fail=1
fi

if command -v node >/dev/null 2>&1; then
  node -v
else
  echo "Falta: node (requerido para frontend/mobile)" >&2
fi

if command -v docker >/dev/null 2>&1; then
  docker --version
else
  echo "docker no detectado (opcional si usas Postgres/Redis locales)" >&2
fi

if command -v psql >/dev/null 2>&1; then
  psql --version
else
  echo "psql no detectado (opcional)" >&2
fi

if command -v redis-cli >/dev/null 2>&1; then
  redis-cli --version
else
  echo "redis-cli no detectado (opcional)" >&2
fi

exit "$fail"

