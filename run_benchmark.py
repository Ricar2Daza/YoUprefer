import subprocess
import sys
import os

# Cambiar al directorio backend
os.chdir('backend')

# Ejecutar el benchmark
try:
    result = subprocess.run([sys.executable, 'scripts/bench_perf.py'], 
                          capture_output=True, text=True, cwd='backend')
    
    print("=== RESULTADOS DEL BENCHMARK ===")
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    print(f"Código de salida: {result.returncode}")
    
except Exception as e:
    print(f"Error ejecutando benchmark: {e}")
    sys.exit(1)