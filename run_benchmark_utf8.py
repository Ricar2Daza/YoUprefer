import os
import sys

# Establecer encoding UTF-8 para evitar problemas de Unicode
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Ejecutar el benchmark con encoding UTF-8
print("🚀 Ejecutando benchmark con UTF-8...")

try:
    # Ejecutar con shell y redirección de salida
    import subprocess
    
    # Cambiar al directorio backend
    os.chdir('backend')
    
    # Ejecutar el benchmark
    process = subprocess.Popen([
        sys.executable, 'scripts/bench_perf.py'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    
    stdout, stderr = process.communicate()
    
    print("=== RESULTADOS DEL BENCHMARK ===")
    if stdout:
        print(stdout)
        
        # Parsear resultados
        lines = stdout.strip().split('\n')
        results = {}
        for line in lines:
            if ':' in line and not line.startswith('==='):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    results[key] = value
        
        if results:
            print("\n📊 RESUMEN DE RESULTADOS:")
            print(f"Ranking (primera llamada): {results.get('ranking_first_ms', 'N/A')} ms")
            print(f"Ranking (segunda llamada): {results.get('ranking_second_ms', 'N/A')} ms")
            print(f"Pair (primera llamada): {results.get('pair_first_ms', 'N/A')} ms")
            print(f"Pair (segunda llamada): {results.get('pair_second_ms', 'N/A')} ms")
            print(f"Compresión GZip: {results.get('ranking_encoding', 'N/A')}")
            
            # Calcular mejoras
            try:
                first_ranking = float(results.get('ranking_first_ms', 0))
                second_ranking = float(results.get('ranking_second_ms', 0))
                first_pair = float(results.get('pair_first_ms', 0))
                second_pair = float(results.get('pair_second_ms', 0))
                
                if first_ranking > 0:
                    ranking_improvement = round((1 - second_ranking/first_ranking) * 100, 1)
                    print(f"Mejora Ranking: {ranking_improvement}%")
                
                if first_pair > 0:
                    pair_improvement = round((1 - second_pair/first_pair) * 100, 1)
                    print(f"Mejora Pair: {pair_improvement}%")
                    
            except (ValueError, ZeroDivisionError):
                pass
            
    if stderr:
        print("\n=== ERRORES ===")
        print(stderr)
    
    print(f"\n=== CÓDIGO DE SALIDA: {process.returncode} ===")
    
    if process.returncode == 0 and stdout.strip():
        print("\n✅ Benchmark ejecutado exitosamente!")
    else:
        print("\n❌ El benchmark falló o no produjo salida")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()