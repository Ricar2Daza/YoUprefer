# Documentación Técnica del Sistema YoUprefer

## 1. Introducción
YoUprefer (anteriormente Carómetro) es una plataforma de votación social basada en comparaciones directas (pairwise ranking) al estilo Elo. Los usuarios suben fotos ("perfiles") para competir en rankings globales o categorizados. El sistema incluye gamificación (insignias), notificaciones en tiempo real y gestión de usuarios.

## 2. Arquitectura del Sistema
- **Backend**: Python 3.11+ + FastAPI (incluye capas async y sync).
- **Frontend**: Next.js (App Router) + Tailwind CSS. La versión exacta en el repo está en `frontend/package.json`.
- **Mobile**: Expo (React Native) + expo-router. La versión exacta en el repo está en `mobile/package.json`.
- **Base de Datos**: PostgreSQL + SQLAlchemy + Alembic.
- **Caché/Session**: Redis (gestión de tokens, blacklist, caché y PubSub).
- **Almacenamiento**: Cloudflare R2 para imágenes (S3 compatible).

## 3. Módulos del Sistema Existentes

### 3.1. Autenticación (`auth`)
- **Funcionalidad**: Registro, Login (OAuth2 Password Bearer), Refresh Token, Logout (Blacklist en Redis), Recuperación de contraseña.
- **Tecnologías**: JWT (HS256), Passlib (pbkdf2_sha256), Redis.
- **Seguridad**: Hashing seguro, expiración corta de access tokens (30 min), revocación mediante blacklist.

### 3.2. Gestión de Usuarios (`users`)
- **Funcionalidad**: Perfil básico, Seguir/Dejar de seguir, Listado de seguidores/siguiendo.
- **Nueva Característica**: Subida de Avatar independiente de las fotos de ranking, Gestión de perfil (actualización de información básica), Gestión de categorías (creación, actualización, eliminación).

### 3.3. Gestión de Perfiles/Ranking (`profiles`)
- **Funcionalidad**: Subida de fotos para competir, Listado de ranking (Global/Categoría), Eliminación/Salida del ranking, Gestión de categorías (asignación a usuarios), Gestión de insignias (asignación a usuarios), Gestión de eventos (creación, actualización, eliminación), Gestión de temporadas (creación, actualización, eliminación), Gestión de K-factor (actualización dinámica).
- **Lógica**: Solo se permite una foto activa por usuario a la vez para evitar spam y mantener la equidad.

### 3.4. Sistema de Votación (`votes`)
- **Funcionalidad**: Voto A vs B. Cálculo de Elo (K-factor dinámico o fijo). Registro de historial de votos.
- **Rendimiento**: Transacciones atómicas para actualizar puntuaciones.

### 3.5. Gamificación (`badges`)
- **Funcionalidad**: Asignación automática de insignias basada en eventos (ej. "Primera Victoria", "Racha de 10", "Top 10", "Más Votado", "Top 10 Categoría", "Más Votado Categoría", "Top 10 Global", "Más Votado Global", "Top 10 Categoría Global", "Más Votado Categoría Global",).
- **Implementación**: Listeners de eventos o chequeos periódicos.

### 3.6. Notificaciones (`notifications`)
- **Funcionalidad**: Alertas en tiempo real (polling o SSE/WebSockets) sobre nuevos seguidores, insignias ganadas, etc.

### 3.7. Administración (`admin`)
- **Funcionalidad**: Moderación de fotos (Aprobar/Rechazar), Reset de temporadas, Gestión de usuarios (banear/suspender), Gestión de categorías, Gestión de insignias, Gestión de notificaciones, Gestión de eventos, Gestión de roles (admin/user), Gestión de permisos, Gestión de configuraciones (K-factor, temporadas), Gestión de logs, Gestión de estadísticas, Gestión de backups, Gestión de restauración de backups.

---

## 4. Características Adicionales Implementadas (Detalle Técnico)

A continuación se detallan los módulos solicitados y recientemente implementados/mejorados.

### 4.1. Módulo de Gestión de Fotos en Ranking
**Objetivo**: Garantizar la integridad del ranking permitiendo solo una participación activa por usuario.

**Requisitos Técnicos**:
- **Unicidad**: Restricción a nivel de base de datos y lógica de negocio para impedir `is_active=True` múltiple por `user_id`.
- **Validación**: Comprobación tanto de fotos "Aprobadas" como "Pendientes" para evitar duplicados en cola de moderación.
- **Feedback UI**: Bloqueo proactivo en el frontend si el usuario ya participa.

**Implementación**:
- **Backend**: Modificación en `POST /profiles/upload-direct` para consultar existencia de perfil activo/pendiente.
- **Frontend**: Página `/upload` consulta estado (`/profiles/me/participation-status`) y renderiza condicionalmente el formulario o el mensaje de estado.
- **Tecnologías**: FastAPI Dependency Injection, SQLAlchemy `select().where(or_(...))`.

**Consideraciones**:
- **Seguridad**: Validación en servidor es mandatoria (no confiar solo en frontend).
- **Rendimiento**: Índice compuesto en `(user_id, is_active)` para consultas rápidas.
- **Dificultad**: Media (requiere sincronización estado frontend-backend y manejo de condiciones de carrera).

### 4.2. Módulo de Perfil de Usuario Completo
**Objetivo**: Centralizar la identidad del usuario y su progreso.

**Requisitos Técnicos**:
- **Avatar**: Almacenamiento separado de las fotos de ranking (`avatars/` vs `profiles/`).
- **Relaciones**: Contadores eficientes de seguidores/seguidos.
- **Interactividad**: Edición in-place de avatar y datos personales.

**Implementación**:
- **Backend**: Nuevo campo `avatar_url` en modelo `User`. Endpoint `POST /users/me/avatar`.
- **Frontend**: Página `/profile` rediseñada con carga de imagen asíncrona, previsualización y contadores.
- **Tecnologías**: `UploadFile` en FastAPI, `FormData` en React, `next/image` optimizado.

**Consideraciones**:
- **Escalabilidad**: Las imágenes se sirven desde CDN/S3, no desde el servidor de aplicaciones.
- **Seguridad**: Validación de tipos MIME (solo imágenes) y tamaño máximo.
- **Dificultad**: Media (integración de subida de archivos y gestión de estado UI).

---

## 5. Propuestas de Futuras Mejoras (Clasificación por Dificultad)

### Nivel Bajo
1.  **Modo Oscuro/Claro**: Implementar theme switcher en Tailwind.
2.  **Compartir en Redes Sociales**: Botones para compartir perfil o ranking en Twitter/Facebook/WhatsApp.
3.  **Filtros de Ranking**: Ordenar por "Más votados", "Mejor racha", "Más recientes".

### Nivel Medio
4.  **Comentarios en Perfiles**: Sistema de comentarios anidados en las fotos de ranking.
    - *Req*: Nueva tabla `comments`, endpoints CRUD, moderación básica.
5.  **Búsqueda de Usuarios**: Barra de búsqueda con autocompletado.
    - *Req*: Endpoint de búsqueda con `ILIKE` o Full-Text Search en Postgres.
6.  **Reporte de Usuarios**: Sistema para reportar contenido inapropiado.

### Nivel Alto
7.  **App Móvil Nativa (React Native)**: Portar la experiencia a iOS/Android.
    - *Req*: API REST ya existente facilita esto, pero requiere desarrollo de UI nativa.
8.  **Chat en Tiempo Real**: Mensajería directa entre usuarios que se siguen.
    - *Req*: WebSockets (Socket.io o FastAPI WebSockets), persistencia de mensajes (MongoDB/Postgres).
9.  **Sistema de Torneos**: Eventos temporales con reglas específicas y premios únicos.
    - *Req*: Lógica compleja de programación, brackets de eliminación, gestión de estados de torneo.
10. **Análisis de Imagen con IA**: Moderación automática de contenido (NSFW) antes de subir.
    - *Req*: Integración con APIs de visión (AWS Rekognition, Google Vision) o modelos locales (TensorFlow/PyTorch).

---

## 6. Estrategia de Pruebas (Unitarias + Integración)

### 6.1. Objetivos y Criterios de Éxito
- **Cobertura mínima**: 80% (líneas, statements, funciones, branches) en:
  - Backend (paquete `app`) mediante `pytest-cov`.
  - Frontend (código bajo `src/lib`, `src/context`, `src/components`) mediante Jest.
- **Criterios de calidad**:
  - Todas las pruebas deben ser deterministas (sin flakiness por tiempo/red/orden).
  - Pruebas unitarias sin dependencias externas (DB/Redis/S3 reales).
  - Pruebas de integración validan flujos entre módulos (API ↔ DB ↔ caché) usando entornos aislados.

### 6.2. Separación de Entornos de Prueba

**Backend**
- Por defecto, las pruebas usan **SQLite** aislado y efímero mediante fixtures que sobrescriben dependencias de DB:
  - [conftest.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/tests/conftest.py)
- Variables opcionales para ejecutar integración con Postgres:
  - `TEST_DATABASE_URL`
  - `ASYNC_TEST_DATABASE_URL`

**Frontend**
- Entorno `jest-environment-jsdom` con mocks de:
  - `fetch`, `localStorage`, `WebSocket`, `FileReader`, `Image`, `canvas.toBlob` (según el caso).
- Base URL de API configurable con `NEXT_PUBLIC_API_URL`.

### 6.3. Plan de Pruebas Unitarias (Ejemplos / Casos Cubiertos)

**Backend (unit)**
- Seguridad y tokens JWT:
  - Hash/verificación de contraseña, manejo de hashes inválidos.
  - Claims obligatorios (`sub`, `type`, `exp`) en access/refresh tokens.
  - Casos: [test_security_unit.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/tests/test_security_unit.py)
- Configuración:
  - Sanitización de `DATABASE_URL` (comillas/BOM) y rechazo de SQLite en runtime.
  - Parseo de CORS desde string JSON.
  - Casos: [test_config_unit.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/tests/test_config_unit.py)
- Rate limit:
  - Bloqueo al exceder límite.
  - Resolución de clave por `user_id` cuando hay Bearer token.
  - Casos: [test_ratelimit_unit.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/tests/test_ratelimit_unit.py)

**Frontend (unit)**
- Cliente HTTP:
  - Refresh proactivo por expiración cercana y uso del token nuevo.
  - Refresh forzado ante 401 y retry con token actualizado.
  - Propagación del mensaje `detail` desde errores JSON.
  - Casos: [api.test.ts](file:///c:/Users/Usuario/Desktop/Carometro/frontend/src/lib/api.test.ts)
- Realtime:
  - URL ws derivada desde `NEXT_PUBLIC_API_URL`.
  - Parsing de mensajes JSON y fallback a string.
  - Casos: [realtime.test.ts](file:///c:/Users/Usuario/Desktop/Carometro/frontend/src/lib/realtime.test.ts)
- Utilidades:
  - Merge de clases (Tailwind) y filtrado de falsy values.
  - Casos: [utils.test.ts](file:///c:/Users/Usuario/Desktop/Carometro/frontend/src/lib/utils.test.ts)
- Compresión/validación de imágenes:
  - Validación de tipo/tamaño.
  - Compresión con stubs de `FileReader`/`Image`/canvas.
  - Casos: [imageCompression.test.ts](file:///c:/Users/Usuario/Desktop/Carometro/frontend/src/lib/imageCompression.test.ts)

### 6.4. Plan de Pruebas de Integración (Escenarios Críticos)

**Backend (integración API + DB)**
- Autenticación y sesión:
  - Registro → Login → Refresh → Logout → reintentos controlados.
  - Casos: [test_auth.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/tests/test_auth.py)
- Flujo completo (MVP):
  - Registro/Inicio de sesión → obtención de par → voto → verificación de categorías.
  - Casos: [test_integration_flow.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/tests/test_integration_flow.py)
- Participación/subida:
  - Subida de perfil → participación activa → restricciones de re-subida.
  - Casos: [test_participation.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/tests/test_participation.py)

**Frontend (integración por componentes)**
- (Base) integraciones del cliente HTTP con localStorage + refresh + retry.
- (Realtime) conexión ws y entrega de eventos a capas superiores.

### 6.5. Ejecución Local y Reportes de Cobertura

**Backend**
- Ejecutar pruebas:
  - `python -m pytest`
- Ejecutar con cobertura (80% mínimo):
  - `python -m pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=80`

**Frontend**
- Ejecutar pruebas:
  - `npm test`
- Ejecutar con cobertura (80% mínimo):
  - `npm run test:coverage`

### 6.6. Automatización CI/CD
- Pipeline propuesto: GitHub Actions ejecutando:
  - Backend: instalación + `pytest` con cobertura y umbral mínimo.
  - Frontend: lint + jest con cobertura + build.
- Reportes: publicación como artifacts (`coverage.xml` backend y `lcov` frontend).
- Notificaciones: fallos visibles en PR/Checks; opcional integración a Slack vía secret `SLACK_WEBHOOK_URL`.
