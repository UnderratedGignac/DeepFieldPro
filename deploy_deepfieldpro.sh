#!/bin/bash
# DeepFieldPro Production Deployment Script & Cron Architecture

# ==========================================
# 1. Daily Data Ingestion (Runs at 04:00 UTC)
# ==========================================
# Fetches all match logs, odds, and advanced tables from the previous day.
# 0 4 * * * /usr/bin/python3 /opt/DeepFieldPro/src/data/wc_scraper.py --daily
# 30 4 * * * /usr/bin/python3 /opt/DeepFieldPro/src/data/advanced_fbref_scraper.py --daily

# ==========================================
# 2. Feature Generation (Runs at 05:30 UTC)
# ==========================================
# Triggers the massive ETL pipeline to update the offline Feature Store
# 30 5 * * * /usr/bin/python3 /opt/DeepFieldPro/src/features/generate_all.py

# ==========================================
# 3. Model Retraining (Runs weekly on Monday at 08:00 UTC)
# ==========================================
# Re-fits the LightGBM models with the latest week of variance
# 0 8 * * 1 /usr/bin/python3 /opt/DeepFieldPro/src/models/train_prop_model.py

# ==========================================
# 4. Live Prediction Service (Runs every 15 mins during match days)
# ==========================================
# Queries live API odds, grabs latest weather, generates predictions, and pushes to Dashboard
# */15 12-22 * * 5,6,7 /usr/bin/python3 /opt/DeepFieldPro/src/inference/run_live_predictions.py

echo "Deployment Architecture Designed. Run via CRON."
