#!/bin/bash
# Mide CPU/RSS/GPU del servicio con TODAS las mascotas activas, en un entorno aislado
# (copia de la biblioteca en $BENCH_DIR; no toca tu biblioteca real).
# Uso: bench_run.sh <ruta_codigo|installed> [segundos_medicion] [espera_arranque]
CODE=${1:-installed}; N=${2:-20}; WAIT=${3:-12}
BD=${BENCH_DIR:?define BENCH_DIR con home/ data/ config/}
export HOME=$BD/home XDG_DATA_HOME=$BD/data XDG_CONFIG_HOME=$BD/config DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent
cd /tmp
if [ "$CODE" = installed ]; then unset PYTHONPATH; else export PYTHONPATH=$CODE; fi
python -m animalinux --daemon >$BD/out.log 2>&1 &
PID=$!
sleep $WAIT
tck=$(getconf CLK_TCK)
t1=$(awk '{print $14+$15}' /proc/$PID/stat); v1=$(grep -h ctxt /proc/$PID/status | awk '{s+=$2} END{print s}')
sleep $N
t2=$(awk '{print $14+$15}' /proc/$PID/stat); v2=$(grep -h ctxt /proc/$PID/status | awk '{s+=$2} END{print s}')
rss=$(awk '/VmRSS/{printf "%.0f", $2/1024}' /proc/$PID/status)
gpu=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null | awk -F, -v p=$PID '$1+0==p{print $2}')
wins=$(hyprctl layers -j | python3 -c "import json,sys;print(sum(1 for m in json.load(sys.stdin).values() for ls in m['levels'].values() for x in ls if x['pid']==$PID and 'mascot' in x['namespace']))")
sizes=$(hyprctl layers -j | python3 -c "import json,sys;print(sorted({(x['w'],x['h']) for m in json.load(sys.stdin).values() for ls in m['levels'].values() for x in ls if x['pid']==$PID and 'mascot' in x['namespace']}))")
echo "CODE=$CODE cpu=$(echo "scale=1; ($t2-$t1)*100/$tck/$N" | bc)% rss=${rss}MB gpu=${gpu} ventanas=$wins tamaños=$sizes despertares/s=$(( (v2-v1)/N ))"
pkill -P $PID; kill $PID 2>/dev/null; sleep 1; kill -9 $PID 2>/dev/null
