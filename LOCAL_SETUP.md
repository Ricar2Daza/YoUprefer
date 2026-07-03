# YoUprefer — Setup local (macOS) con PostgreSQL y Redis

Este documento guía la ejecución local del backend (FastAPI) conectado a **PostgreSQL** y **Redis** en tu Mac.

## 1. Requisitos
- Python 3.11+ recomendado (mínimo práctico: 3.10+, porque el código usa `str | None`).
- Node.js 18+ (frontend).
- PostgreSQL 13+ (servicio local).
- Redis 6+ (servicio local).

## 2. Variables de entorno (backend)
El backend carga configuración desde un archivo `.env` (por defecto) vía [config.py](file:///Users/nuevomac/Documents/YoUprefer/backend/app/core/config.py).

En desarrollo local, crea tu propio archivo:
- `backend/.env` (NO debe commitearse)

Puedes partir de:
- `backend/.env.example`

Variables mínimas recomendadas (ejemplo, sin valores reales):
```env
PROJECT_NAME=YoUprefer
API_V1_STR=/api/v1

SECRET_KEY=__GENERAR_UN_SECRET_LARGO__

DATABASE_URL=postgresql://__USER__:__PASSWORD__@localhost:5432/__DBNAME__

REDIS_HOST=localhost
REDIS_PORT=6379

# CORS (en dev puedes listar tus orígenes)
# BACKEND_CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

Notas:
- `DATABASE_URL` se acepta directa; si no se define, se arma desde `POSTGRES_*`. Ver [config.py](file:///Users/nuevomac/Documents/YoUprefer/backend/app/core/config.py).
- Las funciones de upload a R2 usan `R2_*`. Para smoke test local puedes omitirlas si no vas a probar subidas directas.

## 3. Preparar PostgreSQL (local)
Objetivo: tener un rol/usuario, una base y permisos.

Ejemplo (adaptar a tu instalación):
1. Crear DB:
   - DB: `youprefer` (o `carometro`, si quieres usar el default actual).
2. Asegurar que `DATABASE_URL` apunte a esa DB.

Diagnóstico básico:
- Si tienes `psql`, verifica conectividad:
  - `psql "postgresql://USER:PASSWORD@localhost:5432/DBNAME" -c "select 1;"`

## 4. Preparar Redis (local)
El backend usa Redis para:
- Blacklist de tokens (logout/revocación).
- Cache de endpoints (ranking/pair/participación).
- PubSub para notificaciones realtime.

Diagnóstico básico:
- Si tienes `redis-cli`:
  - `redis-cli ping` → debe devolver `PONG`

## 5. Backend: instalación, migraciones y arranque

### 5.1 Instalar dependencias
Desde `backend/`:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5.2 Ejecutar migraciones (Alembic) en PostgreSQL
Alembic usa la URL configurada y fuerza driver sync para migraciones. Ver [alembic/env.py](file:///Users/nuevomac/Documents/YoUprefer/backend/alembic/env.py).

Desde `backend/`:
```bash
alembic upgrade head
```

Si hay error de conexión:
- Revisa que `DATABASE_URL` sea correcta.
- Revisa que Postgres esté levantado y acepte conexiones locales.

### 5.3 Levantar la API
Desde `backend/`:
```bash
uvicorn app.main:app --reload
```

Checks:
- `GET http://127.0.0.1:8000/health` → `{ "status": "healthy" }`
- `GET http://127.0.0.1:8000/docs` → UI de Swagger

## 6. Frontend web (Next.js)
La web usa `NEXT_PUBLIC_API_URL` para apuntar al backend. Por defecto, el cliente usa `http://127.0.0.1:8000/api/v1` (ver [api.ts](file:///Users/nuevomac/Documents/YoUprefer/frontend/src/lib/api.ts)).

Desde `frontend/`:
```bash
npm ci
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1 npm run dev
```

Checks:
- Abrir `http://localhost:3000`
- Probar registro/login y carga de páginas que consumen API.

## 7. Mobile (Expo)
La app móvil usa `EXPO_PUBLIC_API_URL` (ver [mobile/lib/api.ts](file:///Users/nuevomac/Documents/YoUprefer/mobile/lib/api.ts)).

Desde `mobile/`:
```bash
npm ci
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1 npm run start
```

Nota Android emulator:
- Si usas emulador Android, suele requerirse `http://10.0.2.2:8000/api/v1` en lugar de `127.0.0.1` (hay fallback implementado).

## 8. Troubleshooting rápido
- 401 constantes en web:
  - Revisa hora del sistema, `SECRET_KEY` consistente, y que el refresh endpoint esté disponible.
- Problemas CORS en navegador:
  - Define `BACKEND_CORS_ORIGINS` con los orígenes reales (localhost:3000).
- WebSocket no conecta:
  - Confirma que el backend expone `WS /api/v1/ws/notifications` y que el token se envía como query param.
- Redis caído:
  - Algunas funciones degradan sin cache, pero blacklist/pubsub puede dejar de funcionar.
