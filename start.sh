#!/bin/bash
set -e

echo "🤖 Starting ARIA Stock Agent..."

# Create data directories if missing
mkdir -p data/cache data/reports

# Start background scheduler (weekday 08:45 IST morning + 19:00 IST evening)
#python main.py --schedule &
#SCHED_PID=$!
#echo "   Scheduler PID: $SCHED_PID"

# Launch Streamlit dashboard (foreground — keeps container alive)
echo "   Launching dashboard on :8501"
exec streamlit run dashboard/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false
