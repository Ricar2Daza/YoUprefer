# Plan de Infraestructura, Nube y Rollback

Estado objetivo: llevar YoUprefer a producción en la nube con CI/CD basado en Git
Trunk, contenedores con Podman, registro de imágenes, infraestructura como código
(IaC), monitoreo y estrategias de rollback probadas.

## 0. Lo que ya está hecho

- CI/CD en GitHub Actions (`.github/workflows/ci.yml`), metodología **Trunk-Based**:
  - Rama larga única: `main`.
  - Devs crean **ramas cortas** (`feat/x`, `fix/y`) y abren PR hacia `main`.
  - Cualquier `push` (a cualquier rama) y cualquier PR hacia `main` ejecutan el
    pipeline: backend (pytest + cobertura ≥80%), frontend (lint + tests + build),
    mobile (tests Expo).
  - El push a `main` (trunk) dispara además el **CD**: build con **Podman** y push
    de la imagen `ghcr.io/<owner>/youprefer-api:{main,<sha>}` a GHCR.
  - Protección recomendada de `main`: exigir PR + 1 review + checks verdes.

## 1. Registry de contenedores

| Opción | Costo | Notas |
|---|---|---|
| **GHCR (actual)** | Gratis | Ya integrado. Paquetes privados por defecto: publicar la imagen hace el deploy más fácil. |
| ECR (AWS) | Pagado (por GB) | Útil si la computación es AWS (misma red, permisos IAM nativos). |
| Azure ACR / GCP Artifact Registry | Pagado | Solo si eliges Azure/GCP. |
| Cloudflare (no tiene registry) | — | R2 no es registry; se usa para objetos (fotos). |

**Decisión**: empezar con **GHCR**; migrar a **ECR** si la nube elegida es AWS
(para ping local y menos pasos de login).

## 2. Computación en la nube (la pieza que falta)

Comparativa para un backend FastAPI + WebSockets + filas de fotos en R2:

| Proveedor | Ideal para | Costo inicial | Complejidad |
|---|---|---|---|
| **AWS (ECS Fargate)** | Producción robusta, alta disponibilidad, integración Terraform | ~15-40 USD/mes | Media/Alta |
| Cloudflare Workers/Container | Si el servidor fuera serverless puro; con WebSockets + Postgres sostenidos es incómodo | — | Alta (no es el mejor fit) |
| Azure / GCP | Equivalente a AWS con sus propios matices | ~igual a AWS | Media/Alta |
| **Railway / Fly.io / VPS+Caddy** | Arranque rápido y barato mientras no hay tráfico | ~5-15 USD/mes | Baja |
| Render / Heroku | Sencillos, pero peor para WebSockets y control | ~7-20 USD/mes | Baja |

**Recomendación**: entrar por la vía rápida (Railway o VPS+Docker+Podman+Caddy
dentro de Cloudflare) para lanzar, y dejar el **Plan AWS** (Terraform ya orientado
a VPC + RDS + ElastiCache + ECS Fargate) como el blanco de producción. No hay
cuenta AWS ahora: el plan IaC queda listo para aplicarse cuando la abras.

## 3. IaC (Infraestructura como Código)

- Herramienta: **Terraform** (o **OpenTofu**, fork gratis). El `terraform/` se
  borró y se regenerará con una base mínima, sin asumir recursos de pago.
- **Estado remoto**: bucket de estado bloqueado (S3 + DynamoDB lock en AWS;
  alternativa: `terraform cloud` free tier). Nunca estado local sin protección.
- Estructura por vidas: `stages/` (dev, staging, prod) + módulos (network, db,
  cache, compute, dns).
- Flujo: `terraform plan` en **PR** (job de CI dry-run) → `terraform apply` en
  **CD** al desplegar a staging/prod. El plan/apply se versiona y se revisa.
- Inmutabilidad: los servidores se reemplazan (imagen nueva) en vez de modificarse
  a mano (nada de SSH a producción).

## 4. Monitoreo

Capas mínimas (gratis al principio):

1. **Logs**: JSON estructurado en la API (`logging` a stdout) → recolectados por
   el host (o CloudWatch/Stackdriver) con rotación. Nada de logs en BD.
2. **Métricas**: Prometheus exponiendo `/metrics` (latencia p95, P99, errores 5xx,
   RPS, cola de WebSockets) + Grafana. Alertas en Slack/email.
3. **Uptime/sintéticos**: UptimeRobot/Healthchecks.io llamando a `/health` cada
   minuto (Postgres y Redis ya se reportan ahí).
4. **Errores**: Sentry (`sentry-sdk`) para excepciones del backend y del frontend.
5. **Tracing** (solo si crece): OpenTelemetry → Jaeger/tempo.

Indicadores a vigilar: uso de conexiones Postgres, memoria JVM/RSS del API,
tamaño de claves en Redis (tokens), % de caché R2, latencia p95 del ranking.

## 5. Estrategias de rollback (aterrizadas al stack)

Regla de oro: **la versión anterior es una imagen publicada siempre desplegable**.

| Estrategia | Cómo | Cuándo usarla |
|---|---|---|
| **Rolling (default)** | El orquestador sube instancias nuevas y retira viejas (ECS drained / Railway). | Deploy normal. |
| **Rollback por imagen** | Redeploy de la etiqueta `:main` anterior (GHCR conserva todo `<sha>`; nunca sobrescribas `:main` con fuerza, siempre nueva ref). | Error grave post-deploy. Es el primero y suficiente el 80% de veces. |
| **Blue/Green** | Dos ambientes vivos; se corta el DNS/lb al verde e inmediatamente se vuelve al azul si falla. | Cambios grandes de esquema o frontend. |
| **Canary** | 5-10% del tráfico a la versión nueva y se observa 10-15 min; luego 100%. | Cambios de alto riesgo (ELO, auth, mensajería). |
| **Feature flags** | La funcionalidad nueva queda apagada con `if flag ON`. Rollback sin desplegar. | Funciones aislables (badges, nuevas categorías). |
| **Rollback de BD** | **Nunca** revertir espejando el esquema. Las migraciones se escriben para ser **aditivas/reversibles** (`alembic downgrade` solo en emergencia); los datos dañados se recuperan con **backup + point-in-time recovery** del RDS. | Emergencia de datos. |

Detalles que lo hacen real:
- Cada deploy corre `alembic upgrade head` ANTES de arrancar el API nuevo (job de
  CD separado), y solo con migraciones compatibles hacia atrás.
- Backups automatizados de RDS (7-30 días) + test de restauración mensual.
- Las migraciones se prueban en staging primero; si una no es reversible, requiere
  plan de alto riesgo y canary obligatorio.

## 6. Roadmap sugerido

| Fase | Entregable | Orden |
|---|---|---|
| 0 | Trunk + CI/CD+Podman+GHCR (hecho) | 1 |
| 1 | Proteger `main`, `Containerfile` probado localmente con Podman, imagen pública en GHCR | 2 |
| 2 | Alojamiento básico (Railway con la imagen GHCR) + Postgres/Redis managed + dominio + TLS | 3 |
| 3 | IaC mínima (Terraform) que describa exactamente ese hosting, estado remoto, plan en PR | 4 |
| 4 | Monitoreo (Prometheus+Grafana, Sentry, Healthchecks) + migraciones automáticas en CD | 5 |
| 5 | Estrategias de rollout (blue/green o canary según lo que decidas) + runbook de rollback | 6 |
| 6 | AWS ECS Fargate + RDS + ElastiCache + CloudWatch/GuardDuty | Cuando haya cuenta AWS |

Cada fase autocontiene su propio rollback (regla: al terminar una fase, se puede
volver a la fase anterior con menos de 15 minutos).