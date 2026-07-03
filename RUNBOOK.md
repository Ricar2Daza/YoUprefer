# YoUprefer â€” Runbook (arranque, checks y detenciÃ³n segura)

## Dependencias externas
- Python 3.10+ (recomendado 3.11+)
- Node.js 18+ (frontend)
- PostgreSQL 13+ y Redis 6+
- Alternativa reproducible: Docker Desktop (para `docker compose`)

## Variables de entorno
- Backend: copia `backend/.env.example` â†’ `backend/.env` y ajusta `SECRET_KEY` y `DATABASE_URL`.
- Frontend: copia `frontend/.env.local.example` â†’ `frontend/.env.local`.
- Mobile: copia `mobile/.env.example` â†’ `mobile/.env` (si vas a ejecutar Expo).

## Arranque (modo Docker, recomendado)
1. Levantar servicios (Postgres + Redis):
   - `bash scripts/dev-up.sh`
2. Migraciones (una vez):
   - `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
   - `alembic upgrade head`
3. Backend:
   - `uvicorn app.main:app --reload`
4. ValidaciÃ³n de salud:
   - `curl -s http://127.0.0.1:8000/health | python -m json.tool`
5. Frontend:
   - `cd frontend && npm ci && npm run dev`
   - Abrir `http://localhost:3000`

## Arranque (modo servicios locales)
1. Asegurar que Postgres y Redis estÃ©n levantados (en tu Mac).
2. Seguir los pasos 2â€“5 del modo Docker.

## SeÃ±ales y logs de arranque
- El backend registra `startup.begin` y `startup.ready` con flags `postgres_ok` y `redis_ok`.
- Si Postgres/Redis no estÃ¡n disponibles, `/health` responde `degraded` con detalles de error.

## DetenciÃ³n segura
- Backend/Frontend/Mobile (procesos en terminal): `Ctrl+C`.
- Servicios Docker:
  - `bash scripts/dev-down.sh`
