"""
config.py - 統一設定檔，讀取 .env 環境變數
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Shioaji API ---
SHIOAJI_API_KEY = os.getenv("SHIOAJI_API_KEY", "")
SHIOAJI_SECRET_KEY = os.getenv("SHIOAJI_SECRET_KEY", "")

# --- Google Gemini AI ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# --- 交易費用 ---
BROKER_FEE_RATE = float(os.getenv("BROKER_FEE_RATE", "0.001425"))
BROKER_FEE_DISCOUNT = float(os.getenv("BROKER_FEE_DISCOUNT", "0.6"))
TAX_RATE_STOCK = float(os.getenv("TAX_RATE_STOCK", "0.003"))
TAX_RATE_ETF = float(os.getenv("TAX_RATE_ETF", "0.001"))

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- 伺服器 ---
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# --- 交易時間 ---
TRADING_SESSIONS = {
    "pre_market":  ("08:30", "09:00"),
    "market":      ("09:00", "13:30"),
    "after_hours": ("13:40", "14:30"),
}

# --- 資料庫 ---
DB_PATH = os.path.join(os.path.dirname(__file__), "stock_game.db")
