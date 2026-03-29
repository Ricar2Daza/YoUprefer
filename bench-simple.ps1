# Script simple para ejecutar benchmarks y actualizar documentación
param([switch]$Verbose)

Write-Host "🚀 Iniciando benchmark de rendimiento..." -ForegroundColor Green

# Cambiar al directorio del proyecto
$projectRoot = "C:\Users\Usuario\Desktop\Carometro"
Set-Location $projectRoot

Write-Host "📊 Ejecutando benchmarks..." -ForegroundColor Yellow

# Ejecutar el benchmark
cd backend
$output = python scripts/bench_perf.py 2>&1
$exitCode = $LASTEXITCODE

cd ..

if ($exitCode -ne 0) {
    Write-Error "El benchmark falló con código: $exitCode"
    Write-Error $output
    exit $exitCode
}

if ($Verbose) {
    Write-Host "Salida del benchmark:" -ForegroundColor Cyan
    Write-Host $output -ForegroundColor Gray
}

# Parsear resultados
$results = @{}
foreach ($line in $output -split "`n") {
    $line = $line.Trim()
    if ($line -match "^(\w+):\s*(.+)$") {
        $results[$matches[1]] = $matches[2]
    }
}

Write-Host "✅ Benchmark completado exitosamente" -ForegroundColor Green

# Calcular mejoras
$rankingImprovement = 0
$pairImprovement = 0

if ([double]$results['ranking_first_ms'] -gt 0) {
    $rankingImprovement = [math]::Round((1 - [double]$results['ranking_second_ms']/[double]$results['ranking_first_ms']) * 100, 0)
}

if ([double]$results['pair_first_ms'] -gt 0) {
    $pairImprovement = [math]::Round((1 - [double]$results['pair_second_ms']/[double]$results['pair_first_ms']) * 100, 0)
}

# Crear resultados
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$resultsText = @"

## Resultados del Benchmark - $timestamp

| Metrica | Valor (ms) | Mejora |
|---------|------------|--------|
| Ranking (primera llamada) | $($results['ranking_first_ms']) | - |
| Ranking (segunda llamada) | $($results['ranking_second_ms']) | ${rankingImprovement}% |
| Pair (primera llamada) | $($results['pair_first_ms']) | - |
| Pair (segunda llamada) | $($results['pair_second_ms']) | ${pairImprovement}% |
| Compresion GZip | $($results['ranking_encoding']) | ✓ |

> **Nota**: Los benchmarks se ejecutan con base de datos SQLite de prueba. Los tiempos pueden variar en produccion.

---

"@

Write-Host "📝 Actualizando documento..." -ForegroundColor Yellow

# Anexar al documento
$docPath = "$projectRoot\PERFORMANCE_OPTIMIZATIONS.md"
Add-Content -Path $docPath -Value $resultsText -Encoding UTF8

Write-Host "✅ Documento actualizado exitosamente" -ForegroundColor Green
Write-Host "📄 Resultados añadidos a: $docPath" -ForegroundColor Cyan

Write-Host "🎉 Proceso completado!" -ForegroundColor Green
Write-Host ""
Write-Host "Resumen:" -ForegroundColor White
Write-Host "  • Ranking: $($results['ranking_first_ms'])ms → $($results['ranking_second_ms'])ms (${rankingImprovement}% mejora)" -ForegroundColor Gray
Write-Host "  • Pair: $($results['pair_first_ms'])ms → $($results['pair_second_ms'])ms (${pairImprovement}% mejora)" -ForegroundColor Gray
Write-Host "  • Compresion: $($results['ranking_encoding'])" -ForegroundColor Gray