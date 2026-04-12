# YoUprefer

## Documentación clave
- Reporte técnico (arquitectura/BD/stack/requisitos/seguridad): [TECHNICAL_REPORT.md](file:///Users/nuevomac/Documents/YoUprefer/TECHNICAL_REPORT.md)
- Guía de ejecución local con PostgreSQL y Redis (macOS): [LOCAL_SETUP.md](file:///Users/nuevomac/Documents/YoUprefer/LOCAL_SETUP.md)
- Runbook (arranque/checks/detención segura): [RUNBOOK.md](file:///Users/nuevomac/Documents/YoUprefer/RUNBOOK.md)
- Documentación técnica histórica: [TECHNICAL_DOCUMENTATION.md](file:///Users/nuevomac/Documents/YoUprefer/TECHNICAL_DOCUMENTATION.md)

## Ejecución local (paso a paso)
Este repositorio incluye:
- **Backend**: FastAPI + SQLAlchemy + Alembic (`backend/`)
- **Frontend**: Next.js (`frontend/`)
- **Mobile**: Expo (opcional) (`mobile/`)

La forma más simple de replicar el entorno local es levantar **PostgreSQL + Redis** (vía Docker Compose o instalados en tu sistema), correr migraciones y arrancar backend + frontend.

### 0) Requisitos previos (sistema)
**Versiones recomendadas**
- Python **3.11+** (mínimo práctico: 3.10+)
- Node.js **18+**
- PostgreSQL **13+**
- Redis **6+**

**macOS**
- Node: instala Node 18+ (por ejemplo con `nvm`) y verifica:
  - `node --version`, `npm --version`
- Python: usa `python3 --version`
- Opcional (recomendado): Docker Desktop (para levantar Postgres/Redis rápido)

**Linux (Ubuntu/Debian)**
- Asegura `python3`, `python3-venv`, `build-essential`, Node 18+, Postgres y Redis (o Docker).

**Windows**
- Recomendado: WSL2 (Ubuntu) + Docker Desktop.

### 1) Servicios: PostgreSQL + Redis
Puedes elegir una de estas opciones:

#### Opción A (recomendada): Docker Compose
Desde la raíz del repo:
```bash
./scripts/dev-up.sh
```

Verifica que los servicios estén arriba:
```bash
docker compose ps
```

Puertos por defecto:
- PostgreSQL: `localhost:5432` (usuario `postgres`, password `postgres`, DB `${POSTGRES_DB:-youprefer}`)
- Redis: `localhost:6379`

Si quieres que Docker cree la DB `carometro`:
```bash
POSTGRES_DB=carometro ./scripts/dev-up.sh
```
Luego usa `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/carometro` en `backend/.env`.

Para detener:
```bash
./scripts/dev-down.sh
```

Logs (útil para diagnosticar Postgres/Redis):
```bash
./scripts/dev-logs.sh
```

#### Opción B: Servicios instalados localmente
Si ya tienes Postgres y Redis instalados, asegúrate de:
- PostgreSQL escuchando en `localhost:5432`
- Redis escuchando en `localhost:6379`

Valores típicos en local (ajusta a tu caso):
- Usuario: `postgres`
- Password: `postgres`
- DB: `carometro` (recomendado para este proyecto)

**Ejemplo (crear DB `carometro`)**
```sql
CREATE DATABASE carometro;
```

Verifica conectividad a Postgres:
```bash
psql "postgresql://postgres:postgres@localhost:5432/carometro" -c "select 1;"
```
Salida esperada:
```text
 ?column?
----------
        1
```

Diagnóstico básico:
```bash
redis-cli ping
```
Salida esperada:
```text
PONG
```

#### Opción C (modo mínimo): SQLite + FakeRedis (sin Postgres/Redis)
Este modo es útil si quieres arrancar rápido sin instalar/levantar servicios. No es equivalente a producción, pero sirve para UI y flujos básicos.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ALLOW_SQLITE=true DATABASE_URL=sqlite:///./youprefer.db alembic upgrade head
ALLOW_SQLITE=true DATABASE_URL=sqlite:///./youprefer.db uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2) Backend (FastAPI)
#### 2.1 Configurar variables de entorno
El backend carga configuración desde `backend/.env` (no se commitea). Parte desde:
```bash
cd backend
cp .env.example .env
```

Edita `backend/.env` con valores locales. Mínimo recomendado:
```env
PROJECT_NAME=YoUprefer
API_V1_STR=/api/v1

SECRET_KEY=__CAMBIAR_EN_LOCAL__

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/carometro

REDIS_HOST=localhost
REDIS_PORT=6379

BACKEND_CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

Notas:
- `DATABASE_URL` debe apuntar a tu DB real (por ejemplo `carometro`).
- Si Redis no está disponible, el backend hace fallback automático a FakeRedis en memoria para desarrollo, pero se recomienda Redis real para probar realtime/blacklist.

#### 2.2 Instalar dependencias (Python)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### 2.3 Migraciones (Alembic)
```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```
Salida esperada (ejemplo):
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

#### 2.4 Levantar API
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Salida esperada (ejemplo):
```text
Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

#### 2.5 Checks rápidos
Health:
```bash
curl -sS http://127.0.0.1:8000/health
```
Salida esperada (ejemplo):
```json
{"status":"healthy","postgres":{"ok":true,"error":null},"redis":{"ok":true,"error":null}}
```

Swagger:
- `http://127.0.0.1:8000/docs`

#### 2.6 (Opcional) Seed de datos de demo
```bash
cd backend
source .venv/bin/activate
python scripts/seed_all.py
```

### 3) Frontend web (Next.js)
#### 3.1 Variables de entorno
El frontend lee `frontend/.env.local` (no se commitea). Parte desde:
```bash
cd frontend
cp .env.local.example .env.local
```

Valor recomendado:
```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
```

#### 3.2 Instalar dependencias y arrancar
```bash
cd frontend
npm ci
npm run dev -- --port 3000
```

Salida esperada (ejemplo):
```text
- Local: http://localhost:3000
✓ Ready in ...
```

Abre:
- `http://localhost:3000`

### 4) Mobile (opcional, Expo)
```bash
cd mobile
npm ci
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1 npm run start
```

Nota Android emulator:
- suele requerir `http://10.0.2.2:8000/api/v1` en lugar de `127.0.0.1`.

### 5) Ejecutar tests y lint (recomendado antes de abrir PR)
Backend:
```bash
cd backend
source .venv/bin/activate
pytest
```

Frontend:
```bash
cd frontend
npm run lint
npm test -- --runInBand
```

### 6) Troubleshooting (problemas comunes)
**1) `Address already in use` (puertos 8000/3000 ocupados)**
- Cambia el puerto o mata el proceso que lo está usando.
  - Backend: `--port 8001`
  - Frontend: `-- --port 3001`

**2) Error de conexión a PostgreSQL**
- Verifica `DATABASE_URL` en `backend/.env` y que Postgres esté levantado.
- Asegura que la DB existe (ej. `carometro`) y el usuario/clave coinciden.

**3) CORS en navegador**
- Asegura `BACKEND_CORS_ORIGINS` incluye `http://localhost:3000`.

**4) Redis no conecta**
- Confirma `redis-cli ping` devuelve `PONG`.
- Si no hay Redis, el backend usa FakeRedis (útil para desarrollo, pero no sustituye pruebas de realtime/blacklist).

**5) 401 constantes / problemas de login**
- Revisa que `SECRET_KEY` en `backend/.env` no cambie entre reinicios si ya emitiste tokens.
- Confirma que el frontend apunta al API correcta vía `NEXT_PUBLIC_API_URL`.

**6) WebSocket de notificaciones no conecta**
- Confirma que el backend está arriba y que el endpoint de WS existe:
  - `ws://127.0.0.1:8000/api/v1/ws/notifications?token=...`

## Ejecución rápida (TL;DR)
Servicios (Docker):
```bash
./scripts/dev-up.sh
```

Backend:
```bash
cd backend
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:
```bash
cd frontend
cp .env.local.example .env.local
npm ci
npm run dev -- --port 3000
```
