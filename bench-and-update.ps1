<#
.SYNOPSIS
    Ejecuta benchmarks de rendimiento y actualiza el documento de optimizaciones.

.DESCRIPTION
    Este script ejecuta el benchmark de rendimiento del backend y anexa los resultados
    al documento PERFORMANCE_OPTIMIZATIONS.md con marca de tiempo automática.
    
    Requisitos:
    - Python 3.8+ con entorno virtual activado
    - Dependencias del backend instaladas (pip install -r requirements.txt)
    - Base de datos SQLite de prueba configurada

.EXAMPLE
    .\bench-and-update.ps1
    
.EXAMPLE
    .\bench-and-update.ps1 -Verbose
#>

param(
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Iniciando benchmark de rendimiento..." -ForegroundColor Green

# Verificar que estamos en el directorio correcto
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if ($Verbose) {
    Write-Host "Directorio del proyecto: $projectRoot" -ForegroundColor Cyan
}

# Verificar que existe el script de benchmark
$benchScript = Join-Path $projectRoot "backend" "scripts" "bench_perf.py"
if (-not (Test-Path $benchScript)) {
    Write-Error "No se encontró el script de benchmark: $benchScript"
    exit 1
}

# Verificar que existe el documento de optimizaciones
$docPath = Join-Path $projectRoot "PERFORMANCE_OPTIMIZATIONS.md"
if (-not (Test-Path $docPath)) {
    Write-Error "No se encontró el documento de optimizaciones: $docPath"
    exit 1
}

Write-Host "📊 Ejecutando benchmarks..." -ForegroundColor Yellow

# Ejecutar el benchmark y capturar la salida
try {
    # Cambiar al directorio backend para ejecutar el benchmark
    Push-Location (Join-Path $projectRoot "backend")
    
    $output = python scripts/bench_perf.py 2>&1
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -ne 0) {
        Write-Error "El benchmark falló con código de salida: $exitCode"
        Write-Error "Salida del error: $output"
        exit $exitCode
    }
    
    if ($Verbose) {
        Write-Host "Salida del benchmark:" -ForegroundColor Cyan
        Write-Host $output -ForegroundColor Gray
    }
    
    Pop-Location
}
catch {
    Write-Error "Error ejecutando el benchmark: $_"
    if ((Get-Location).Path -ne $projectRoot) {
        Pop-Location
    }
    exit 1
}

Write-Host "✅ Benchmark completado exitosamente" -ForegroundColor Green

# Parsear los resultados del benchmark
$results = @{}
foreach ($line in $output -split "`n") {
    $line = $line.Trim()
    if ($line -match "^(\w+):\s*(.+)$") {
        $key = $matches[1]
        $value = $matches[2]
        $results[$key] = $value
    }
}

# Calcular mejoras porcentuales
$rankingImprovement = 0
$pairImprovement = 0

if ([double]$results['ranking_first_ms'] -gt 0) {
    $rankingImprovement = [math]::Round((1 - [double]$results['ranking_second_ms']/[double]$results['ranking_first_ms']) * 100, 0)
}

if ([double]$results['pair_first_ms'] -gt 0) {
    $pairImprovement = [math]::Round((1 - [double]$results['pair_second_ms']/[double]$results['pair_first_ms']) * 100, 0)
}

# Crear la sección de resultados con timestamp
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "📝 Actualizando documento de optimizaciones..." -ForegroundColor Yellow

# Anexar resultados al documento usando un enfoque más simple
try {
    # Crear el contenido línea por línea para evitar problemas de parsing
    $content = "`n`n## Resultados del Benchmark - $timestamp`n`n"
    $content += "| Metrica | Valor (ms) | Mejora |`n"
    $content += "|---------|------------|--------|`n"
    $content += "| Ranking (primera llamada) | $($results['ranking_first_ms']) | - |`n"
    $content += "| Ranking (segunda llamada) | $($results['ranking_second_ms']) | ≈$rankingImprovement% |`n"
    $content += "| Pair (primera llamada) | $($results['pair_first_ms']) | - |`n"
    $content += "| Pair (segunda llamada) | $($results['pair_second_ms']) | ≈$pairImprovement% |`n"
    $content += "| Compresion GZip | $($results['ranking_encoding']) | ✓ |`n`n"
    $content += "> **Nota**: Los benchmarks se ejecutan con base de datos SQLite de prueba. Los tiempos pueden variar en produccion.`n`n"
    $content += "---`n"
    
    Add-Content -Path $docPath -Value $content -Encoding UTF8
    Write-Host "✅ Documento actualizado exitosamente" -ForegroundColor Green
    Write-Host "📄 Resultados añadidos a: $docPath" -ForegroundColor Cyan
}
catch {
    Write-Error "Error actualizando el documento: $_"
    exit 1
}

Write-Host "🎉 Proceso completado exitosamente!" -ForegroundColor Green
Write-Host ""
Write-Host "Resumen de resultados:" -ForegroundColor White
Write-Host "  • Ranking: $($results['ranking_first_ms'])ms → $($results['ranking_second_ms'])ms" -ForegroundColor Gray
Write-Host "  • Pair: $($results['pair_first_ms'])ms → $($results['pair_second_ms'])ms" -ForegroundColor Gray
Write-Host "  • Compresion: $($results['ranking_encoding'])" -ForegroundColor Gray