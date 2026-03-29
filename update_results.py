import datetime
import subprocess
import sys
import os
import re

os.environ["PYTHONIOENCODING"] = "utf-8"

def run_benchmark():
    cwd = os.getcwd()
    try:
        os.chdir("backend")
        proc = subprocess.Popen(
            [sys.executable, "-u", "scripts/bench_perf.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        stdout, stderr = proc.communicate()
        return proc.returncode, stdout, stderr
    finally:
        os.chdir(cwd)

code, out, err = run_benchmark()

results = {}
for line in (out or "").splitlines():
    m = re.match(r"^(ranking_first_ms|ranking_second_ms|ranking_encoding|pair_first_ms|pair_second_ms)[\s:]+(.+)$", line.strip())
    if m:
        results[m.group(1)] = m.group(2).strip()

ranking_improvement = None
pair_improvement = None

try:
    fr = float(results.get("ranking_first_ms", "0"))
    sr = float(results.get("ranking_second_ms", "0"))
    fp = float(results.get("pair_first_ms", "0"))
    sp = float(results.get("pair_second_ms", "0"))
    if fr > 0:
        ranking_improvement = round((1 - (sr / fr)) * 100, 1)
    if fp > 0:
        pair_improvement = round((1 - (sp / fp)) * 100, 1)
except ValueError:
    pass

timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

lines = []
lines.append("")
lines.append(f"## Resultados del Benchmark - {timestamp}")
lines.append("")
lines.append("| Metrica | Valor (ms) | Mejora |")
lines.append("|---------|------------|--------|")
lines.append(f"| Ranking (primera llamada) | {results.get('ranking_first_ms', 'N/A')} | - |")
lines.append(f"| Ranking (segunda llamada) | {results.get('ranking_second_ms', 'N/A')} | {str(ranking_improvement) + '%' if ranking_improvement is not None else 'N/A'} |")
lines.append(f"| Pair (primera llamada) | {results.get('pair_first_ms', 'N/A')} | - |")
lines.append(f"| Pair (segunda llamada) | {results.get('pair_second_ms', 'N/A')} | {str(pair_improvement) + '%' if pair_improvement is not None else 'N/A'} |")
lines.append(f"| Compresion GZip | {results.get('ranking_encoding', 'N/A')} | {'✓' if results.get('ranking_encoding') == 'gzip' else '✗'} |")
lines.append("")
lines.append("> Nota: Los benchmarks se ejecutan con base de datos SQLite de prueba. Los tiempos pueden variar en produccion.")
lines.append("")
lines.append("---")
lines.append("")

doc_path = "PERFORMANCE_OPTIMIZATIONS.md"
with open(doc_path, "a", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Documento actualizado exitosamente")
print(f"Resultados añadidos a: {doc_path}")
print("Resumen de resultados:")
print(f"  • Ranking: {results.get('ranking_first_ms', 'N/A')}ms → {results.get('ranking_second_ms', 'N/A')}ms")
print(f"  • Pair: {results.get('pair_first_ms', 'N/A')}ms → {results.get('pair_second_ms', 'N/A')}ms")
print(f"  • Compresion: {results.get('ranking_encoding', 'N/A')}")
