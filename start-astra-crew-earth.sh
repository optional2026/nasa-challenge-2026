#!/usr/bin/env bash
# ASTRA two-sided demonstration on one machine (see start-astra-crew-earth.bat / docs/CREW_EARTH_SYNC.md).
set -euo pipefail
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt; else . .venv/bin/activate; fi
python run.py --side earth --reset-db & EARTH=$!
sleep 4
python run.py --side onboard --allow-link-simulation --reset-db & ONBOARD=$!
trap 'kill $ONBOARD $EARTH 2>/dev/null' EXIT INT TERM
echo "Crew Side  : http://127.0.0.1:8000  (vega, okafor = astronauts; mori = CMO)"
echo "Earth Side : http://127.0.0.1:8100  (admin = administrator; ramirez = ground flight surgeon)"
wait
