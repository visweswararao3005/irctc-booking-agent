"""Configuration settings and environment variable management."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Project root directory (Train/)
BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "src" else Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Master encryption key for securing credentials in storage (AES-256)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").strip()

# Polling and Monitoring configuration
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60").strip())

# Cloud Key-Value Storage (Upstash Redis or standard Redis)
REDIS_URL = os.getenv("REDIS_URL", "").strip()
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()

# Browser Automation Mode (Set HEADLESS_BROWSER=true to hide browser, false to view Chrome UI)
HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "false").strip().lower() in ("true", "1", "yes")

# Local Data Fallback Directory
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
