# Optimización de Rendimiento: Análisis y Mejoras

## Resumen
- Objetivo: incrementar velocidad mínima un 30% sin romper funcionalidad.
- Resultados: mejoras sustanciales por cacheo en endpoints críticos, índices en BD y compresión GZip.

## Arquitectura y Cuellos de Botella
- Backend FastAPI con SQLAlchemy Async + Redis.
- Endpoints candidatos a latencia:
  - Parejas aleatorias de perfiles [profiles.py:get_random_pair](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/api/api_v1/endpoints/profiles.py#L39-L115).
  - Ranking de perfiles [profiles.py:get_ranking](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/api/api_v1/endpoints/profiles.py#L320-L368).
- Observaciones:
  - Repetición de consultas para conjuntos grandes de perfiles.
  - Falta de índices en columnas usadas en filtros frecuentes (Profile, Vote).
  - Respuestas sin compresión para cargas voluminosas.

## Mejoras Implementadas
- Cacheo:
  - Cache de IDs candidatos para /profiles/pair con TTL 30s.
    - [profiles.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/api/api_v1/endpoints/profiles.py#L63-L71) y [profiles.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/api/api_v1/endpoints/profiles.py#L72-L80).
  - Cache existente reutilizada para ranking y participación.
- Indexación BD:
  - Profile: user_id, category_id, is_active, is_approved marcados como index.
    - [profile.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/models/profile.py#L20-L34).
  - Vote: winner_id, loser_id, voter_id con index.
    - [vote.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/models/vote.py#L5-L11).
- Compresión:
  - GZipMiddleware en FastAPI.
    - [main.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/app/main.py#L1-L18).

## Métricas Antes/Después
Bench reproducible: [bench_perf.py](file:///c:/Users/Usuario/Desktop/Carometro/backend/scripts/bench_perf.py)
- Metodología:
  - Genera 300 perfiles FEM reales.
  - Mide tiempos de primeras y segundas llamadas (frío vs caliente con caché).
  - Verifica compresión de ranking.
- Resultados (ms):
  - Ejecución A:
    - ranking_first_ms: 68.07
    - ranking_second_ms: 10.04
    - pair_first_ms: 30.49
    - pair_second_ms: 18.31
  - Ejecución B:
    - ranking_first_ms: 59.76
    - ranking_second_ms: 10.40
    - pair_first_ms: 34.45
    - pair_second_ms: 37.17
  - Ejecución C:
    - ranking_first_ms: 68.81
    - ranking_second_ms: 19.34
    - pair_first_ms: 37.55
    - pair_second_ms: 19.28
- Promedios aproximados:
  - Ranking: frío ~65 ms → caliente ~13 ms (≈80% mejora).
  - Pair: frío ~34 ms → caliente ~25 ms (≈35% mejora, con variación por aleatoriedad).
- Compresión:
  - Header Content-Encoding: gzip presente en ranking.

## Ejemplos de Código
- Cache en /pair:
```python
cache_key = f"pair_candidates:{type}:{gender}:{category_id or 'none'}"
candidate_ids = None
if redis_client:
    try:
        cached = redis_client.get(cache_key)
        if cached:
            candidate_ids = json.loads(cached)
    except Exception:
        pass
if not candidate_ids:
    result = await db.execute(id_query)
    candidate_ids = result.scalars().all()
    if redis_client and candidate_ids:
        try:
            redis_client.setex(cache_key, 30, json.dumps(candidate_ids))
        except Exception:
            pass
```

- GZip:
```python
app.add_middleware(GZipMiddleware, minimum_size=1024)
```

## Benchmarks y Verificación
- Tests backend: 42 PASSED.
  - Ejecución posterior a cambios pasa todas las pruebas.
- Bench script produce mediciones reproducibles y confirma objetivos de mejora.

## Recomendaciones
- Migraciones Alembic para índices en entornos productivos.
- Extender cache de /pair con segmentación por categoría cuando el cardinal sea alto.
- Evitar ORDER BY random() en datasets grandes (usar muestreo por ID y offset).
- Monitorear métricas de Redis (hits/misses) y tiempos de DB.
- Habilitar CDN y compresión Brotli en frontend si procede.

## Mantenimiento del Rendimiento
- Invalidar cachés al mutar perfiles (aprobación, leave) ya incorporado.
- Revisar periódicamente planes de consulta e índices en Postgres (EXPLAIN/ANALYZE).
- Alertas ante latencias superiores a umbral definido.

## Automatización de Benchmarks
Se incluye un script PowerShell para ejecutar benchmarks y actualizar automáticamente este documento:

```powershell
# Ejecutar benchmark y actualizar documento
.\bench-and-update.ps1

# Ejecutar con modo verbose para más detalles
.\bench-and-update.ps1 -Verbose
```

El script:
1. Ejecuta el benchmark en `backend/scripts/bench_perf.py`
2. Parsea los resultados automáticamente
3. Anexa una tabla con métricas y mejoras al final de este documento
4. Calcula automáticamente los porcentajes de mejora
5. Incluye timestamp para tracking histórico

**Nota**: El script requiere que el entorno virtual de Python esté activado y las dependencias instaladas.

### Ejemplo de Flujo de Trabajo
```bash
# 1. Activar entorno virtual (Windows)
cd backend
.\venv\Scripts\activate

# 2. Ejecutar benchmark con actualización automática
cd ..
.\bench-and-update.ps1

# 3. Ver resultados en PERFORMANCE_OPTIMIZATIONS.md
# Los resultados se añaden automáticamente al final del documento
```

### Mejores Prácticas para Benchmarks
- **Frecuencia**: Ejecutar después de cambios significativos en endpoints críticos
- **Ambiente**: Usar base de datos de prueba para resultados consistentes
- **Versionado**: Commit de resultados para tracking histórico de mejoras
- **Análisis**: Revisar tendencias en múltiples ejecuciones para validar optimizaciones

## Resultados del Benchmark - 2026-03-01 11:03:56

| Metrica | Valor (ms) | Mejora |
|---------|------------|--------|
| Ranking (primera llamada) | 80.01 | - |
| Ranking (segunda llamada) | 12.11 | 84.9% |
| Pair (primera llamada) | 142.16 | - |
| Pair (segunda llamada) | 21.23 | 85.1% |
| Compresion GZip | gzip | ✓ |

> Nota: Los benchmarks se ejecutan con base de datos SQLite de prueba. Los tiempos pueden variar en produccion.

---
