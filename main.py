"""
main.py - 台股戰情室 一鍵啟動
啟動 FastAPI + Shioaji Worker + 法人籌碼排程 + AI 引擎 + 到價提醒 + 融資融券 + Telegram + 績效 + 集保
python main.py 即可啟動所有服務
"""
import sys
import os
import io

# 修正 Windows 終端 Unicode 編碼問題（cp950 不支援 emoji）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio
import uvicorn
import webbrowser
import threading
import time
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import SERVER_HOST, SERVER_PORT
from database.db import init_database
from workers.shioaji_worker import worker as shioaji_worker
from workers.institutional_worker import institutional_worker
from workers.ai_analyzer import ai_analyzer
from workers.alert_manager import alert_manager
from workers.margin_worker import margin_worker
from workers.telegram_bot import telegram_bot
from workers.tdcc_worker import tdcc_worker

# --- 第一階段路由 ---
from routes.routes_stock import router as stock_router
from routes.routes_watchlist import router as watchlist_router
from routes.routes_trade import router as trade_router
from routes.routes_institutional import router as institutional_router
from routes.routes_diary import router as diary_router

# --- 第二階段路由 ---
from routes.routes_ai import router as ai_router
from routes.routes_alert import router as alert_router
from routes.routes_margin import router as margin_router

# --- 第三階段路由 ---
from routes.routes_performance import router as performance_router
from routes.routes_settings import router as settings_router
from routes.routes_tdcc import router as tdcc_router


# ==========================================
# Lifespan 管理
# ==========================================
@asynccontextmanager
async def lifespan(app):
    # --- Startup ---
    print("=" * 50)
    print("  [Stock] 台股戰情室 v3.0 啟動中...")
    print("=" * 50)

    # 1. 初始化資料庫
    await init_database()

    # 2. 啟動 Shioaji Worker（背景行情引擎）
    shioaji_worker.start()

    # 3. 啟動法人籌碼排程（每日 18:05）
    institutional_worker.start()

    # 4. 啟動 AI 分析引擎（每日 18:15 自動檢討）
    ai_analyzer.start()

    # 5. 融資融券排程（掛到法人 Worker 的排程器裡，18:10 抓取）
    institutional_worker.scheduler.add_job(
        margin_worker.fetch_margin_data,
        trigger="cron",
        hour=18,
        minute=10,
        id="fetch_margin",
        replace_existing=True
    )

    # 6. 到價提醒 - 掛載到 Shioaji Worker 的快取更新回呼（含 Telegram 推播）
    _original_fetch = shioaji_worker.fetch_snapshots

    def fetch_with_alerts(stock_ids):
        results = _original_fetch(stock_ids)
        if results:
            triggered = alert_manager.check_alerts(results)
            # Telegram 推播到價提醒
            if triggered and telegram_bot.is_ready():
                for t in triggered:
                    telegram_bot.notify_alert_triggered(
                        t.get("stock_id", ""),
                        t.get("stock_name", ""),
                        t.get("alert_type", ""),
                        t.get("target_price", 0),
                        t.get("current_price", 0)
                    )
        return results

    shioaji_worker.fetch_snapshots = fetch_with_alerts

    # 7. Telegram 通知掛載 - 法人抓完後推播
    _original_inst_fetch = institutional_worker.scheduled_fetch

    def inst_fetch_with_tg():
        _original_inst_fetch()
        if telegram_bot.is_ready():
            from database.models import get_market_institutional
            market_data = get_market_institutional()
            if market_data:
                telegram_bot.notify_institutional_done(
                    market_data.get("date", ""),
                    market_data
                )

    institutional_worker.scheduled_fetch = inst_fetch_with_tg

    # 8. Telegram 通知掛載 - AI 檢討完後推播
    _original_ai_review = ai_analyzer.scheduled_daily_review

    def ai_review_with_tg():
        _original_ai_review()
        if telegram_bot.is_ready() and ai_analyzer.last_review_date:
            from database.models import get_diary
            diary = get_diary(ai_analyzer.last_review_date)
            review_text = diary.get("ai_review", "") if diary else ""
            telegram_bot.notify_ai_review_done(
                ai_analyzer.last_review_date,
                review_text
            )

    ai_analyzer.scheduled_daily_review = ai_review_with_tg

    # 9. 集保大戶排程（每週五 18:30）
    institutional_worker.scheduler.add_job(
        _tdcc_weekly_fetch,
        trigger="cron",
        day_of_week="fri",
        hour=18,
        minute=30,
        id="fetch_tdcc",
        replace_existing=True
    )

    # 10. 初始化 Telegram Chat ID（從 DB 讀取）
    _init_telegram_chat_id()

    print("=" * 50)
    print(f"  [OK] 所有服務已啟動！v3.0（含績效/日曆/TG通知/集保/回測）")
    print(f"  [Web] 請開啟瀏覽器：http://localhost:{SERVER_PORT}")
    print("  [Schedule]")
    print("    - 行情更新：盤中每 15 秒")
    print("    - 法人籌碼：每日 18:05")
    print("    - 融資融券：每日 18:10")
    print("    - AI 檢討：每日 18:15")
    print("    - 集保大戶：每週五 18:30")
    print(f"  [Telegram] {'已就緒' if telegram_bot.is_ready() else '未設定 Chat ID（請到設定頁設定）'}")
    print("=" * 50)

    yield  # App 運行中

    # --- Shutdown ---
    print("\n正在關閉服務...")
    shioaji_worker.stop()
    institutional_worker.stop()
    ai_analyzer.stop()
    print("[OK] 所有服務已安全關閉")


def _tdcc_weekly_fetch():
    """每週五抓取集保大戶資料"""
    from database.models import get_watchlist
    watchlist = get_watchlist()
    stock_ids = [w["stock_id"] for w in watchlist]
    if stock_ids:
        tdcc_worker.fetch_and_save(stock_ids)


def _init_telegram_chat_id():
    """從 DB 讀取 Telegram Chat ID（如果有）"""
    try:
        from database.db import get_db_sync
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
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'telegram_chat_id'"
            ).fetchone()
            if row and dict(row)["value"]:
                telegram_bot.set_chat_id(dict(row)["value"])
        finally:
            conn.close()
    except Exception as e:
        print(f"[TG] 初始化 Chat ID 失敗: {e}")


# ==========================================
# 建立 FastAPI App
# ==========================================
app = FastAPI(
    title="台股戰情室",
    description="即時行情 + 交易紀錄 + 法人籌碼 + AI分析 + 到價提醒 + 績效總覽 + 日曆 + TG通知 + 集保大戶",
    version="3.0.0",
    lifespan=lifespan
)

# 掛載靜態檔案
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 註冊所有路由 ---
app.include_router(stock_router)
app.include_router(watchlist_router)
app.include_router(trade_router)
app.include_router(institutional_router)
app.include_router(diary_router)
app.include_router(ai_router)
app.include_router(alert_router)
app.include_router(margin_router)
app.include_router(performance_router)
app.include_router(settings_router)
app.include_router(tdcc_router)


# 首頁
@app.get("/")
async def index():
    return FileResponse("static/index.html")


# ==========================================
# 優雅關閉
# ==========================================
def signal_handler(sig, frame):
    print("\n收到中斷信號，正在關閉...")
    shioaji_worker.stop()
    institutional_worker.stop()
    ai_analyzer.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ==========================================
# 啟動
# ==========================================
if __name__ == "__main__":
    # 延遲開啟瀏覽器
    def open_browser():
        time.sleep(3)
        webbrowser.open(f"http://localhost:{SERVER_PORT}")

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="info"
    )
