"""
seed_demo.py - 產生模擬資料，用於展示系統功能（截圖用）
執行方式: python scripts/seed_demo.py
會建立一個全新的 stock_game.db 並填入假資料
"""
import sqlite3
import os
import sys
import random
from datetime import datetime, timedelta

# 加入專案根目錄到 path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB_PATH = os.path.join(ROOT, "stock_game.db")


def create_tables(conn):
    """建立所有資料表"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT NOT NULL,
            stock_name TEXT DEFAULT '',
            category TEXT NOT NULL DEFAULT 'watch',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_id)
        );
        CREATE TABLE IF NOT EXISTS portfolio_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT NOT NULL UNIQUE,
            stock_name TEXT DEFAULT '',
            total_shares INTEGER DEFAULT 0,
            avg_cost REAL DEFAULT 0,
            realized_profit REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT NOT NULL,
            stock_name TEXT DEFAULT '',
            action TEXT NOT NULL,
            shares INTEGER NOT NULL,
            price REAL NOT NULL,
            total_amount REAL NOT NULL,
            fee REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            net_amount REAL DEFAULT 0,
            is_odd_lot INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            traded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
            plan_deviation TEXT DEFAULT '',
            tomorrow_plan TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
        );
        CREATE TABLE IF NOT EXISTS market_institutional (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            foreign_net REAL DEFAULT 0,
            trust_net REAL DEFAULT 0,
            dealer_net REAL DEFAULT 0,
            total_net REAL DEFAULT 0,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
        );
        CREATE TABLE IF NOT EXISTS stock_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT NOT NULL,
            stock_name TEXT DEFAULT '',
            alert_type TEXT NOT NULL,
            target_price REAL NOT NULL,
            is_triggered INTEGER DEFAULT 0,
            triggered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
        );
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
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
        );

        CREATE INDEX IF NOT EXISTS idx_trade_log_stock ON trade_log(stock_id);
        CREATE INDEX IF NOT EXISTS idx_trade_log_date ON trade_log(traded_at);
        CREATE INDEX IF NOT EXISTS idx_institutional_date ON institutional_data(date);
        CREATE INDEX IF NOT EXISTS idx_institutional_stock ON institutional_data(stock_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_stock ON stock_snapshots(stock_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_time ON stock_snapshots(snapshot_at);
        CREATE INDEX IF NOT EXISTS idx_diary_date ON daily_diary(date);
        CREATE INDEX IF NOT EXISTS idx_ai_rec_date ON ai_recommendations(date);
        CREATE INDEX IF NOT EXISTS idx_tdcc_stock ON tdcc_data(stock_id);
        CREATE INDEX IF NOT EXISTS idx_tdcc_date ON tdcc_data(date);
    """)


# ==========================================
# 模擬股票資料
# ==========================================
DEMO_STOCKS = [
    ("2330", "台積電", 950.0),
    ("2454", "聯發科", 1280.0),
    ("2317", "鴻海", 178.0),
    ("2382", "廣達", 285.0),
    ("0050", "元大台灣50", 158.0),
    ("2603", "長榮", 195.0),
    ("3661", "世芯-KY", 2050.0),
    ("2884", "玉山金", 28.5),
]

FEE_RATE = 0.001425
FEE_DISCOUNT = 0.6
TAX_STOCK = 0.003
TAX_ETF = 0.001


def calc_fee(amount):
    return max(1, round(amount * FEE_RATE * FEE_DISCOUNT))


def calc_tax(amount, stock_id):
    rate = TAX_ETF if stock_id.startswith("00") else TAX_STOCK
    return round(amount * rate)


def seed_watchlist(conn):
    """關注清單：5 支持有、3 支觀察"""
    print("  [1/9] 建立觀察清單...")
    data = [
        ("2330", "台積電", "hold", "長期持有核心部位"),
        ("2454", "聯發科", "hold", "AI 晶片題材"),
        ("2317", "鴻海", "hold", "AI 伺服器代工"),
        ("2382", "廣達", "hold", "GB200 受惠股"),
        ("0050", "元大台灣50", "hold", "定期定額 ETF"),
        ("2603", "長榮", "watch", "觀察航運景氣"),
        ("3661", "世芯-KY", "watch", "觀察 AI ASIC 訂單"),
        ("2884", "玉山金", "watch", "金融股觀察"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO watchlist (stock_id, stock_name, category, notes) VALUES (?,?,?,?)",
        data
    )


def seed_portfolio(conn):
    """持倉彙總"""
    print("  [2/9] 建立持倉資料...")
    data = [
        ("2330", "台積電", 5000, 890.5, 15200.0),
        ("2454", "聯發科", 2000, 1150.0, 8500.0),
        ("2317", "鴻海", 3000, 165.0, 3200.0),
        ("2382", "廣達", 2000, 260.0, 0.0),
        ("0050", "元大台灣50", 10000, 148.0, 2100.0),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO portfolio_summary (stock_id, stock_name, total_shares, avg_cost, realized_profit) VALUES (?,?,?,?,?)",
        data
    )


def seed_trades(conn):
    """交易紀錄：過去 30 天約 20 筆"""
    print("  [3/9] 建立交易紀錄...")
    today = datetime.now()
    trades = []

    # 台積電 - 分批買入
    for i, (days_ago, price, shares) in enumerate([
        (28, 880.0, 2000), (21, 895.0, 1000), (14, 905.0, 2000),
    ]):
        dt = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d 09:%02d:00" % (30 + i))
        total = price * shares
        fee = calc_fee(total)
        trades.append(("2330", "台積電", "buy", shares, price, total, fee, 0, total + fee, 0, "", dt))

    # 聯發科 - 買入+部分賣出
    dt1 = (today - timedelta(days=25)).strftime("%Y-%m-%d 10:15:00")
    total1 = 1150.0 * 3000
    fee1 = calc_fee(total1)
    trades.append(("2454", "聯發科", "buy", 3000, 1150.0, total1, fee1, 0, total1 + fee1, 0, "看好 AI 晶片", dt1))

    dt2 = (today - timedelta(days=10)).strftime("%Y-%m-%d 11:20:00")
    total2 = 1290.0 * 1000
    fee2 = calc_fee(total2)
    tax2 = calc_tax(total2, "2454")
    trades.append(("2454", "聯發科", "sell", 1000, 1290.0, total2, fee2, tax2, total2 - fee2 - tax2, 0, "部分停利", dt2))

    # 鴻海 - 買入
    dt3 = (today - timedelta(days=20)).strftime("%Y-%m-%d 09:45:00")
    total3 = 165.0 * 3000
    fee3 = calc_fee(total3)
    trades.append(("2317", "鴻海", "buy", 3000, 165.0, total3, fee3, 0, total3 + fee3, 0, "AI 伺服器題材", dt3))

    # 廣達 - 買入
    dt4 = (today - timedelta(days=15)).strftime("%Y-%m-%d 10:30:00")
    total4 = 260.0 * 2000
    fee4 = calc_fee(total4)
    trades.append(("2382", "廣達", "buy", 2000, 260.0, total4, fee4, 0, total4 + fee4, 0, "GB200 題材", dt4))

    # 0050 定期定額
    for days_ago in [27, 20, 13, 6]:
        dt = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d 09:00:00")
        total = 148.0 * 2500
        fee = calc_fee(total)
        trades.append(("0050", "元大台灣50", "buy", 2500, 148.0, total, fee, 0, total + fee, 0, "定期定額", dt))

    # 長榮 - 短線進出
    dt5 = (today - timedelta(days=12)).strftime("%Y-%m-%d 10:00:00")
    total5 = 188.0 * 2000
    fee5 = calc_fee(total5)
    trades.append(("2603", "長榮", "buy", 2000, 188.0, total5, fee5, 0, total5 + fee5, 0, "短線波段", dt5))

    dt6 = (today - timedelta(days=5)).strftime("%Y-%m-%d 13:00:00")
    total6 = 198.0 * 2000
    fee6 = calc_fee(total6)
    tax6 = calc_tax(total6, "2603")
    trades.append(("2603", "長榮", "sell", 2000, 198.0, total6, fee6, tax6, total6 - fee6 - tax6, 0, "停利出場", dt6))

    # 零股交易
    dt7 = (today - timedelta(days=8)).strftime("%Y-%m-%d 09:10:00")
    total7 = 2050.0 * 100
    fee7 = calc_fee(total7)
    trades.append(("3661", "世芯-KY", "buy", 100, 2050.0, total7, fee7, 0, total7 + fee7, 1, "零股試單", dt7))

    conn.executemany(
        "INSERT INTO trade_log (stock_id, stock_name, action, shares, price, total_amount, fee, tax, net_amount, is_odd_lot, note, traded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        trades
    )


def seed_diary(conn):
    """每日日記：過去 5 個交易日"""
    print("  [4/9] 建立交易日記...")
    today = datetime.now()
    entries = [
        (1, "大盤下跌 120 點，電子股普遍回檔。台積電守住 940 關卡。",
         "今日市場受美股科技股回檔影響下跌，但跌幅有限。建議持續持有核心部位，避免追高。整體操作評分：B+。",
         "今天忍住沒有追高，等待拉回再加碼。", "disciplined", "觀察台積電 940 支撐力道"),
        (2, "大盤反彈 85 點，AI 股領漲。聯發科創近期新高。",
         "AI 題材持續發酵，聯發科、廣達等受惠股表現強勢。建議適度減碼獲利部位。整體操作評分：A。",
         "聯發科部分停利 1000 股，執行力不錯。", "calm", "關注長榮法說會結果"),
        (3, "大盤盤整，成交量萎縮。航運股有轉強跡象。",
         "市場觀望氣氛濃厚，量縮整理。短線可關注航運股反彈機會。整體操作評分：B。",
         "今天沒有操作，耐心等待。", "calm", "等待美國 CPI 數據"),
        (5, "大盤大漲 200 點，外資大買。台積電突破 950。",
         "外資回補帶動大盤上攻，台積電突破關鍵價位。AI 族群全面噴出。整體操作評分：A+。",
         "早上看到跳空就知道今天會很強，可惜沒有加碼。", "greedy", "留意是否過熱需要減碼"),
        (7, "大盤小跌 30 點，個股表現分歧。金融股撐盤。",
         "大盤高檔震盪，漲跌互見。金融股受升息預期帶動表現。建議維持均衡配置。整體操作評分：B。",
         "長榮停利出場，獲利約 1.8 萬。", "disciplined", "下週關注 Fed 利率決議"),
    ]
    for days_ago, summary, review, notes, emotion, plan in entries:
        d = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT OR IGNORE INTO daily_diary (date, market_summary, ai_review, user_notes, emotion_tag, tomorrow_plan) VALUES (?,?,?,?,?,?)",
            (d, summary, review, notes, emotion, plan)
        )


def seed_institutional(conn):
    """法人資料：大盤 + 個股"""
    print("  [5/9] 建立法人籌碼...")
    today = datetime.now()
    now_str = datetime.now().isoformat()

    # 大盤法人 - 近 5 天
    market_data = [
        (1, 125.30, -22.50, -45.80, 57.00),
        (2, -85.60, 15.20, 30.10, -40.30),
        (3, 210.40, -8.70, -120.50, 81.20),
        (5, 350.20, -35.60, -80.30, 234.30),
        (7, -150.80, 42.30, 55.20, -53.30),
    ]
    for days_ago, foreign, trust, dealer, total in market_data:
        d = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT OR IGNORE INTO market_institutional (date, foreign_net, trust_net, dealer_net, total_net, fetched_at) VALUES (?,?,?,?,?,?)",
            (d, foreign, trust, dealer, total, now_str)
        )

    # 個股法人
    stock_inst = [
        ("2330", "台積電", 15000, 8000, 7000, 2000, 3000, -1000, 500, 1200, -700, 5300),
        ("2454", "聯發科", 5000, 2000, 3000, 800, 500, 300, 200, 600, -400, 2900),
        ("2317", "鴻海", 8000, 6000, 2000, 1500, 1000, 500, 300, 800, -500, 2000),
        ("2382", "廣達", 3000, 1500, 1500, 600, 400, 200, 100, 300, -200, 1500),
        ("0050", "元大台灣50", 20000, 15000, 5000, 0, 0, 0, 1000, 2000, -1000, 4000),
    ]
    d = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    for sid, name, fb, fs, fn, tb, ts, tn, db_, ds, dn, total in stock_inst:
        conn.execute(
            "INSERT OR IGNORE INTO institutional_data (date, stock_id, stock_name, foreign_buy, foreign_sell, foreign_net, trust_buy, trust_sell, trust_net, dealer_buy, dealer_sell, dealer_net, total_net) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d, sid, name, fb, fs, fn, tb, ts, tn, db_, ds, dn, total)
        )


def seed_alerts(conn):
    """到價提醒"""
    print("  [6/9] 建立到價提醒...")
    alerts = [
        ("2330", "台積電", "above", 1000.0, 0),
        ("2330", "台積電", "below", 900.0, 0),
        ("2454", "聯發科", "above", 1350.0, 0),
        ("2317", "鴻海", "below", 160.0, 0),
        ("2603", "長榮", "above", 210.0, 0),
    ]
    conn.executemany(
        "INSERT INTO stock_alerts (stock_id, stock_name, alert_type, target_price, is_triggered) VALUES (?,?,?,?,?)",
        alerts
    )


def seed_ai_recommendations(conn):
    """AI 推薦紀錄"""
    print("  [7/9] 建立 AI 推薦...")
    today = datetime.now()
    recs = [
        (3, "2330", "台積電",
         "AI 需求持續成長，先進製程訂單滿載。外資連續買超，技術面突破前高。",
         "10-15%", "1-3個月", 880.0, 1050.0, ""),
        (3, "2454", "聯發科",
         "天璣 9400 打入旗艦市場，AI 邊緣運算晶片需求增。法人持續加碼。",
         "8-12%", "2-4週", 1150.0, 1400.0, ""),
        (3, "3661", "世芯-KY",
         "客製化 ASIC 訂單能見度高，受惠於 AI 大廠自研晶片趨勢。",
         "15-20%", "1-3個月", 1850.0, 2400.0, ""),
        (7, "2603", "長榮",
         "貨櫃運價觸底反彈，紅海繞道效應延續。股價淨值比仍低。",
         "5-10%", "2-4週", 175.0, 215.0, "hit_target"),
        (7, "2382", "廣達",
         "GB200 伺服器代工訂單放量，營收有望季增雙位數。",
         "10-15%", "1-3個月", 240.0, 310.0, ""),
    ]
    for days_ago, sid, name, reason, profit, horizon, sl, tp, result in recs:
        d = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO ai_recommendations (date, stock_id, stock_name, reason, profit_potential, time_horizon, stop_loss_price, target_price, actual_result) VALUES (?,?,?,?,?,?,?,?,?)",
            (d, sid, name, reason, profit, horizon, sl, tp, result)
        )


def seed_margin(conn):
    """融資融券"""
    print("  [8/9] 建立融資融券資料...")
    today = datetime.now()
    d = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    margin_data = [
        (d, "2330", 500, 300, 25000, 100, 50, 3000, 8.5),
        (d, "2454", 200, 150, 8000, 30, 20, 1200, 12.3),
        (d, "2317", 800, 600, 35000, 200, 100, 5000, 15.7),
        (d, "2382", 300, 200, 12000, 50, 30, 2000, 6.2),
        (d, "2603", 1000, 800, 50000, 500, 300, 15000, 22.1),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO margin_data (date, stock_id, margin_buy, margin_sell, margin_balance, short_buy, short_sell, short_balance, day_trade_ratio) VALUES (?,?,?,?,?,?,?,?,?)",
        margin_data
    )


def seed_tdcc(conn):
    """集保大戶資料"""
    print("  [9/9] 建立集保資料...")
    today = datetime.now()
    d = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    for sid, name in [("2330", "台積電"), ("2454", "聯發科")]:
        levels = [
            ("retail", random.randint(300000, 500000), random.randint(1000000, 3000000), round(random.uniform(15, 25), 2)),
            ("medium", random.randint(5000, 15000), random.randint(2000000, 5000000), round(random.uniform(20, 30), 2)),
            ("big", random.randint(500, 2000), random.randint(5000000, 15000000), round(random.uniform(45, 65), 2)),
        ]
        for level, holders, shares, pct in levels:
            conn.execute(
                "INSERT OR IGNORE INTO tdcc_data (date, stock_id, level, holders, shares, percent) VALUES (?,?,?,?,?,?)",
                (d, sid, level, holders, shares, pct)
            )


def main():
    print("=" * 50)
    print("  台股戰情室 - 模擬資料產生器")
    print("=" * 50)

    if os.path.exists(DB_PATH):
        ans = input(f"\n⚠️  資料庫已存在: {DB_PATH}\n   是否覆蓋？(y/N): ").strip().lower()
        if ans != 'y':
            print("取消操作。")
            return
        os.remove(DB_PATH)
        print(f"已刪除舊資料庫。")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    print(f"\n正在建立模擬資料到: {DB_PATH}\n")

    create_tables(conn)
    seed_watchlist(conn)
    seed_portfolio(conn)
    seed_trades(conn)
    seed_diary(conn)
    seed_institutional(conn)
    seed_alerts(conn)
    seed_ai_recommendations(conn)
    seed_margin(conn)
    seed_tdcc(conn)

    conn.commit()
    conn.close()

    print(f"\n✅ 完成！模擬資料已寫入 {DB_PATH}")
    print("   啟動伺服器: python main.py")
    print("   開啟瀏覽器: http://localhost:8000")


if __name__ == "__main__":
    main()
