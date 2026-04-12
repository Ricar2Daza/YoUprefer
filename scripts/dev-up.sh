#!/usr/bin/env bash
set -euo pipefail

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    docker compose up -d
    exit 0
  fi
fi

if command -v docker-compose >/dev/null 2>&1; then
  docker-compose up -d
  exit 0
fi

echo "Docker Compose no está disponible. Instala Docker Desktop o docker-compose." >&2
exit 1

