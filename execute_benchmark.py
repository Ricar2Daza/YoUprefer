import subprocess
import sys
import os

# Ejecutar el benchmark original
print("🚀 Ejecutando benchmark de rendimiento...")

try:
    # Cambiar al directorio backend
    os.chdir('backend')
    
    # Ejecutar el script de benchmark
    result = subprocess.run([
        sys.executable, '-u', 'scripts/bench_perf.py'
    ], capture_output=True, text=True)
    
    print("=== SALIDA ESTÁNDAR ===")
    print(result.stdout)
    
    if result.stderr:
        print("=== SALIDA DE ERROR ===")
        print(result.stderr)
    
    print(f"=== CÓDIGO DE SALIDA: {result.returncode} ===")
    
    if result.returncode == 0 and result.stdout.strip():
        print("\n✅ Benchmark ejecutado exitosamente!")
        
        # Parsear resultados
        lines = result.stdout.strip().split('\n')
        results = {}
        for line in lines:
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    results[key] = value
        
        if results:
            print("\n📊 RESULTADOS PARSEADOS:")
            for key, value in results.items():
                print(f"  {key}: {value}")
        else:
            print("\n⚠️  No se pudieron parsear resultados")
    else:
        print("\n❌ El benchmark falló o no produjo salida")
        
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)