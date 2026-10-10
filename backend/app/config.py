"""Runtime configuration. Everything is env-driven so the same build runs locally and on Akamai Cloud."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

# NWS requires a descriptive User-Agent with contact info.
NWS_USER_AGENT = os.getenv("NWS_USER_AGENT", "ClosureCall/0.1 (hackmidwest2026; closurecall@example.com)")
NWS_BASE = "https://api.weather.gov"
NWPS_BASE = "https://api.water.noaa.gov/nwps/v1"
AIRNOW_BASE = "https://www.airnowapi.org/aq/observation/latLong/current/"
AIRNOW_API_KEY = os.getenv("AIRNOW_API_KEY", "")

# LLM provider for the Strands agent. Akamai Cloud hosted inference is OpenAI-compatible,
# so a base_url + api_key + model_id is all we need. BYOI works the same way.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "")
LLM_ENABLED = bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL_ID)

DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "closurecall.sqlite3")))
STATIC_DIR = Path(os.getenv("STATIC_DIR", str(ROOT.parent / "frontend" / "dist")))

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "12"))
