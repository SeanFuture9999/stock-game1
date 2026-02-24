"""
database/db.py - SQLite 資料庫連線管理
使用 aiosqlite 做非同步操作，避免阻塞 FastAPI
"""
import aiosqlite
import sqlite3
import os
from config import DB_PATH


async def get_db():
    """取得非同步資料庫連線"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")  # 提升並發讀寫效能
    await db.execute("PRAGMA foreign_keys=ON")
    return db


def get_db_sync():
    """取得同步資料庫連線（給 Worker 用）"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_database():
    """初始化資料庫，建立所有資料表"""
    db = await get_db()
    try:
        # ==========================================
        # 1. watchlist - 關注清單（持有 + 關注）
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                category TEXT NOT NULL DEFAULT 'watch',
                -- category: 'hold' = 持有, 'watch' = 關注
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(stock_id)
            )
        """)

        # ==========================================
        # 2. portfolio_summary - 持倉損益彙總
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id TEXT NOT NULL UNIQUE,
                stock_name TEXT DEFAULT '',
                total_shares INTEGER DEFAULT 0,
                avg_cost REAL DEFAULT 0,
                realized_profit REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (stock_id) REFERENCES watchlist(stock_id)
            )
        """)

        # ==========================================
        # 3. trade_log - 交易紀錄（含零股、手續費、稅）
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                action TEXT NOT NULL,
                -- action: 'buy' = 買入, 'sell' = 賣出
                shares INTEGER NOT NULL,
                price REAL NOT NULL,
                total_amount REAL NOT NULL,
                fee REAL DEFAULT 0,
                tax REAL DEFAULT 0,
                net_amount REAL DEFAULT 0,
                is_odd_lot INTEGER DEFAULT 0,
                -- is_odd_lot: 0 = 整股, 1 = 零股
                note TEXT DEFAULT '',
                traded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ==========================================
        # 4. daily_diary - 每日交易日記
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_diary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                market_summary TEXT DEFAULT '',
                ai_review TEXT DEFAULT '',
                user_notes TEXT DEFAULT '',
                reminders TEXT DEFAULT '',
                win_rate_today REAL DEFAULT 0,
                max_loss REAL DEFAULT 0,
                emotion_tag TEXT DEFAULT '',
                -- emotion_tag: 'calm', 'impulsive', 'panic', 'greedy', 'disciplined'
                plan_deviation TEXT DEFAULT '',
                tomorrow_plan TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ==========================================
        # 5. institutional_data - 個股法人籌碼
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS institutional_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                stock_id TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                foreign_buy INTEGER DEFAULT 0,
                foreign_sell INTEGER DEFAULT 0,
                foreign_net INTEGER DEFAULT 0,
                trust_buy INTEGER DEFAULT 0,
                trust_sell INTEGER DEFAULT 0,
                trust_net INTEGER DEFAULT 0,
                dealer_buy INTEGER DEFAULT 0,
                dealer_sell INTEGER DEFAULT 0,
                dealer_net INTEGER DEFAULT 0,
                total_net INTEGER DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, stock_id)
            )
        """)

        # ==========================================
        # 6. market_institutional - 大盤法人買賣超
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_institutional (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                foreign_net REAL DEFAULT 0,
                trust_net REAL DEFAULT 0,
                dealer_net REAL DEFAULT 0,
                total_net REAL DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ==========================================
        # 7. stock_snapshots - 行情快照（盤中快取）
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stock_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                price REAL DEFAULT 0,
                change_price REAL DEFAULT 0,
                change_percent REAL DEFAULT 0,
                volume INTEGER DEFAULT 0,
                total_volume INTEGER DEFAULT 0,
                amount REAL DEFAULT 0,
                high REAL DEFAULT 0,
                low REAL DEFAULT 0,
                open REAL DEFAULT 0,
                close REAL DEFAULT 0,
                buy_price REAL DEFAULT 0,
                sell_price REAL DEFAULT 0,
                vwap REAL DEFAULT 0,
                snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ==========================================
        # 8. stock_alerts - 到價提醒
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stock_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                alert_type TEXT NOT NULL,
                -- alert_type: 'above' = 突破, 'below' = 跌破
                target_price REAL NOT NULL,
                is_triggered INTEGER DEFAULT 0,
                triggered_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ==========================================
        # 9. margin_data - 融資融券
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS margin_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                stock_id TEXT NOT NULL,
                margin_buy INTEGER DEFAULT 0,
                margin_sell INTEGER DEFAULT 0,
                margin_balance INTEGER DEFAULT 0,
                short_buy INTEGER DEFAULT 0,
                short_sell INTEGER DEFAULT 0,
                short_balance INTEGER DEFAULT 0,
                day_trade_ratio REAL DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, stock_id)
            )
        """)

        # ==========================================
        # 10. ai_recommendations - AI 推薦紀錄
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                stock_id TEXT DEFAULT '',
                stock_name TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                profit_potential TEXT DEFAULT '',
                time_horizon TEXT DEFAULT '',
                stop_loss_price REAL DEFAULT 0,
                target_price REAL DEFAULT 0,
                actual_result TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ==========================================
        # 11. app_settings - 應用程式設定（key-value）
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ==========================================
        # 12. tdcc_data - 集保大戶資料
        # ==========================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tdcc_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                stock_id TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT '',
                holders INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                percent REAL DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, stock_id, level)
            )
        """)

        # 建立索引，加速查詢
        await db.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_stock ON trade_log(stock_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_date ON trade_log(traded_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_institutional_date ON institutional_data(date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_institutional_stock ON institutional_data(stock_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_stock ON stock_snapshots(stock_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_time ON stock_snapshots(snapshot_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_diary_date ON daily_diary(date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ai_rec_date ON ai_recommendations(date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tdcc_stock ON tdcc_data(stock_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tdcc_date ON tdcc_data(date)")

        await db.commit()
        print("[DB] 資料庫初始化完成，所有資料表已建立。")

    except Exception as e:
        print(f"[DB] 資料庫初始化失敗: {e}")
        raise
    finally:
        await db.close()
