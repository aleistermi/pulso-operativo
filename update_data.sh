#!/bin/bash
# Weekly data refresh for Pulso Operativo
# Runs fetch_timesheets.py to pull latest BambooHR data

cd "$(dirname "$0")"
export PATH="/opt/anaconda3/bin:$PATH"

echo "$(date): Starting weekly fetch..."
python3 fetch_timesheets.py --days 90
echo "$(date): Done."
