"""Centralized configuration loaded from environment variables.

All settings (DB connections, LLM provider keys, runtime tuning) are read
here once at import time so every service shares the same source of truth.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- PostgreSQL -----------------------------------------------------------
DB_SCHEME = os.getenv("DB_SCHEME", "postgresql")
DB_USERNAME = os.getenv("DB_USERNAME", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5555"))
DB_NAME = os.getenv("DB_NAME", "chat_hist_db")
DB_CONNECT_RETRIES = int(os.getenv("DB_CONNECT_RETRIES", "10"))
DB_CONNECT_RETRY_DELAY = float(os.getenv("DB_CONNECT_RETRY_DELAY", "2.0"))
POSTGRES_DSN = f"{DB_SCHEME}://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Redis ----------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# --- LLM providers --------------------------------------------------------
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai")
LOCAL_LLM = os.getenv("LOCAL_LLM", "gemma2:2b")
LOCAL_MODEL_URL = os.getenv("LOCAL_MODEL_URL", "http://localhost:11434/v1")

# Zhipu AI (GLM) — OpenAI-compatible endpoint.
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
ZHIPU_BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_MODEL = os.getenv("ZHIPU_MODEL", "glm-4-flash")

# --- App runtime ----------------------------------------------------------
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# --- Email alerts (SMTP) --------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes", "on")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "ai-log-agent@localhost")
EMAIL_NOTIFY_TO = os.getenv("EMAIL_NOTIFY_TO", "")
