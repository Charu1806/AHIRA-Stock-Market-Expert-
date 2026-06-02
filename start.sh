#!/bin/bash
set -e

echo "🤖 Starting ARIA Stock Agent..."
mkdir -p data/cache data/reports

# Pre-warm cache so first visitor gets instant results.
# Runs in background — Streamlit starts immediately,
# but cache will be ready within ~60s for the first tab click.
echo "   Pre-warming cache in background…"
python scripts/warm_cache.py &

# Launch Streamlit dashboard (foreground — keeps container alive)
echo "   Launching dashboard on :8501"
exec streamlit run dashboard/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false
