"""Configuration settings and environment variable management."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Project root directory (Train/)
BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "src" else Path(__file__).resolve().parent
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

# Cloud Key-Value Storage (Upstash Redis or standard Redis)
# If provided, bot state, profiles, and tasks survive container redeployments
REDIS_URL = os.getenv("REDIS_URL", "")
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

# Live Payment Gateway Configuration (NPCI UPI Intent, Cashfree & Razorpay)
MERCHANT_UPI_VPA = os.getenv("MERCHANT_UPI_VPA", "7981141441@ybl")
MERCHANT_NAME = os.getenv("MERCHANT_NAME", "IRCTC AI Booking Agent")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID", "")
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY", "")
CASHFREE_ENV = os.getenv("CASHFREE_ENV", "PRODUCTION")

# Directories
DATA_DIR = BASE_DIR / "data"
TICKETS_DIR = BASE_DIR / "tickets"

DATA_DIR.mkdir(parents=True, exist_ok=True)
TICKETS_DIR.mkdir(parents=True, exist_ok=True)
