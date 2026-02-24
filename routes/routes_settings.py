"""
routes/routes_settings.py - 設定頁面 API
功能：
  - 讀取/更新系統設定（key-value 儲存）
  - Telegram Chat ID 偵測與測試
  - 手續費折扣設定
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database.db import get_db_sync
from workers.telegram_bot import telegram_bot
from config import (
    BROKER_FEE_RATE, BROKER_FEE_DISCOUNT,
    TAX_RATE_STOCK, TAX_RATE_ETF,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)

router = APIRouter(prefix="/api/settings", tags=["系統設定"])


# ==========================================
# 資料表操作
# ==========================================

def _ensure_table():
    """確保 app_settings 表存在"""
    conn = get_db_sync()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _get_setting(key: str, default: str = "") -> str:
    conn = get_db_sync()
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return dict(row)["value"] if row else default
    finally:
        conn.close()


def _set_setting(key: str, value: str):
    conn = get_db_sync()
    try:
        conn.execute("""
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))
        conn.commit()
    finally:
        conn.close()


# ==========================================
# API 路由
# ==========================================

@router.get("/")
async def get_settings():
    """取得所有設定"""
    _ensure_table()

    # 從 DB 讀取動態設定，若無則用 .env 預設值
    tg_chat_id = _get_setting("telegram_chat_id", TELEGRAM_CHAT_ID)
    tg_enabled = _get_setting("telegram_enabled", "true")
    fee_discount = _get_setting("broker_fee_discount", str(BROKER_FEE_DISCOUNT))
    ai_provider = _get_setting("ai_provider", "gemini")

    return {
        "status": "ok",
        "data": {
            "telegram": {
                "bot_token_set": bool(TELEGRAM_BOT_TOKEN),
                "bot_username": "",
                "chat_id": tg_chat_id,
                "enabled": tg_enabled == "true"
            },
            "trading": {
                "broker_fee_rate": BROKER_FEE_RATE,
                "broker_fee_discount": float(fee_discount),
                "tax_rate_stock": TAX_RATE_STOCK,
                "tax_rate_etf": TAX_RATE_ETF
            },
            "ai": {
                "provider": ai_provider
            }
        }
    }


class SettingUpdate(BaseModel):
    key: str
    value: str


@router.post("/update")
async def update_setting(setting: SettingUpdate):
    """更新單一設定"""
    _ensure_table()

    allowed_keys = [
        "telegram_chat_id", "telegram_enabled",
        "broker_fee_discount",
        "ai_provider"
    ]

    if setting.key not in allowed_keys:
        raise HTTPException(status_code=400, detail=f"不允許修改此設定: {setting.key}")

    _set_setting(setting.key, setting.value)

    # 即時生效：更新 Telegram Bot 的 Chat ID
    if setting.key == "telegram_chat_id":
        telegram_bot.set_chat_id(setting.value)

    return {"status": "ok", "message": f"設定 {setting.key} 已更新"}


# ==========================================
# Telegram 相關
# ==========================================

@router.post("/telegram/detect")
async def telegram_detect_chat_id():
    """偵測 Telegram Chat ID"""
    result = telegram_bot.detect_chat_id()
    if result.get("success"):
        # 儲存到 DB
        _ensure_table()
        _set_setting("telegram_chat_id", result["chat_id"])
        return {
            "status": "ok",
            "message": f"偵測成功！Chat ID: {result['chat_id']}",
            "data": result
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "偵測失敗"))


@router.post("/telegram/test")
async def telegram_test():
    """發送測試訊息"""
    # 先確保使用最新的 Chat ID
    _ensure_table()
    chat_id = _get_setting("telegram_chat_id", TELEGRAM_CHAT_ID)
    if chat_id:
        telegram_bot.set_chat_id(chat_id)

    if not telegram_bot.is_ready():
        raise HTTPException(status_code=400, detail="Telegram 尚未設定完成（缺少 Chat ID）")

    success = telegram_bot.send_test()
    if success:
        return {"status": "ok", "message": "測試訊息已發送，請查看 Telegram"}
    else:
        raise HTTPException(status_code=500, detail="發送失敗，請檢查設定")


@router.post("/telegram/set-chat-id")
async def telegram_set_chat_id(chat_id: str):
    """手動設定 Chat ID"""
    if not chat_id or not chat_id.strip():
        raise HTTPException(status_code=400, detail="Chat ID 不能為空")

    _ensure_table()
    _set_setting("telegram_chat_id", chat_id.strip())
    telegram_bot.set_chat_id(chat_id.strip())

    return {"status": "ok", "message": f"Chat ID 已設定: {chat_id.strip()}"}
