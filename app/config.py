import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Cargar variables de entorno desde .env
load_dotenv()

# Base directory of the project
BASE_DIR = Path(__file__).parent.parent

# Directory for storing downloads
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# API configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_RELOAD = os.getenv("API_RELOAD", "True").lower() == "true"

# Outbound AI calls (Anthropic / OpenAI). Without an explicit timeout the SDK
# defaults (up to 10 minutes per attempt, plus retries) let one slow call tie
# up a worker for a very long time.
AI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))

# /pdf-to-image conversions allowed at once per process. n8n sends a whole batch
# of letters together; each conversion holds ~100 MB (one decoded newspaper page
# plus pdftoppm), and running them all in parallel got the process OOM-killed.
# Conversions are CPU-bound, so queueing them costs no total throughput.
PDF_TO_IMAGE_MAX_CONCURRENCY = int(os.getenv("PDF_TO_IMAGE_MAX_CONCURRENCY", "2"))

# CORS settings
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
