#!/usr/bin/env bash
set -euo pipefail

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    docker compose down
    exit 0
  fi
fi

if command -v docker-compose >/dev/null 2>&1; then
  docker-compose down
  exit 0
fi

echo "Docker Compose no está disponible." >&2
exit 1

