"""Configuration settings and environment variable management."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Master encryption key for securing credentials in JSON files
# If not present in .env, a fallback static key or generated key will be handled in security.py
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# Payment configuration (Credit Card details)
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_EXPIRY = os.getenv("CARD_EXPIRY", "")  # MM/YY
CARD_CVV = os.getenv("CARD_CVV", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "")

# Polling and Monitoring configuration
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
OTP_TIMEOUT_SECONDS = int(os.getenv("OTP_TIMEOUT_SECONDS", "120"))

# Directories
DATA_DIR = BASE_DIR / "data"
TICKETS_DIR = BASE_DIR / "tickets"

DATA_DIR.mkdir(parents=True, exist_ok=True)
TICKETS_DIR.mkdir(parents=True, exist_ok=True)
