"""
workers/margin_worker.py - 融資融券資料抓取
從 TWSE 抓取信用交易資料（融資/融券/當沖比）
每日盤後自動排程
"""
import httpx
import time
import sqlite3
import traceback
from datetime import datetime, date

from config import DB_PATH
from database.models import get_watchlist


class MarginWorker:
    """融資融券資料抓取引擎"""

    def __init__(self):
        self.last_fetch_date = None
        self.last_fetch_status = "idle"

    # ==========================================
    # TWSE 融資融券 API
    # ==========================================

    def fetch_margin_data(self, date_str: str = None):
        """
        抓取個股融資融券資料
        API: https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date=YYYYMMDD&selectType=ALL
        """
        if not date_str:
            date_str = date.today().strftime("%Y%m%d")
        else:
            date_str = date_str.replace("-", "")

        url = f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={date_str}&selectType=ALL"

        try:
            print(f"[Margin] 抓取融資融券資料: {date_str}")
            resp = httpx.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            data = resp.json()

            if data.get("stat") != "OK" or not data.get("data"):
                print(f"[Margin] 融資融券資料尚未公布: {date_str}")
                return []

            # 取得關注清單
            watchlist = get_watchlist()
            watch_ids = set(w["stock_id"] for w in watchlist)

            if not watch_ids:
                print("[Margin] 關注清單為空，跳過")
                return []

            save_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            results = []
            conn = sqlite3.connect(DB_PATH)

            # data["data"] 融資融券格式：
            # [0]股票代號 [1]股票名稱
            # [2]融資買進 [3]融資賣出 [4]融資現金償還 [5]融資前日餘額 [6]融資今日餘額 [7]融資限額
            # [8]融券買進 [9]融券賣出 [10]融券現金償還 [11]融券前日餘額 [12]融券今日餘額 [13]融券限額
            # [14]資券互抵
            for row in data["data"]:
                try:
                    stock_id = row[0].strip()
                    if stock_id not in watch_ids:
                        continue

                    def parse_int(val):
                        return int(str(val).replace(",", "").strip()) if val else 0

                    margin_buy = parse_int(row[2])
                    margin_sell = parse_int(row[3])
                    margin_balance = parse_int(row[6])
                    short_buy = parse_int(row[8])
                    short_sell = parse_int(row[9])
                    short_balance = parse_int(row[12])
                    offset = parse_int(row[14]) if len(row) > 14 else 0

                    # 當沖比 = 資券互抵 / (融資買+融券賣) * 100
                    total_trade = margin_buy + short_sell
                    day_trade_ratio = round(offset / total_trade * 100, 2) if total_trade > 0 else 0

                    conn.execute(
                        """INSERT INTO margin_data
                           (date, stock_id, margin_buy, margin_sell, margin_balance,
                            short_buy, short_sell, short_balance, day_trade_ratio)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(date, stock_id) DO UPDATE SET
                               margin_buy=excluded.margin_buy,
                               margin_sell=excluded.margin_sell,
                               margin_balance=excluded.margin_balance,
                               short_buy=excluded.short_buy,
                               short_sell=excluded.short_sell,
                               short_balance=excluded.short_balance,
                               day_trade_ratio=excluded.day_trade_ratio,
                               fetched_at=CURRENT_TIMESTAMP""",
                        (save_date, stock_id, margin_buy, margin_sell, margin_balance,
                         short_buy, short_sell, short_balance, day_trade_ratio)
                    )

                    results.append({
                        "stock_id": stock_id,
                        "margin_buy": margin_buy,
                        "margin_sell": margin_sell,
                        "margin_balance": margin_balance,
                        "short_buy": short_buy,
                        "short_sell": short_sell,
                        "short_balance": short_balance,
                        "day_trade_ratio": day_trade_ratio
                    })

                except (ValueError, IndexError) as e:
                    continue

            conn.commit()
            conn.close()

            self.last_fetch_date = save_date
            self.last_fetch_status = "success"
            print(f"[Margin] 已儲存 {len(results)} 檔融資融券資料")
            return results

        except Exception as e:
            self.last_fetch_status = f"error: {e}"
            print(f"[Margin] 抓取融資融券失敗: {e}")
            traceback.print_exc()
            return []

    # ==========================================
    # 查詢
    # ==========================================

    def get_margin_data(self, date_str: str = None, stock_id: str = None):
        """查詢融資融券資料"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            if stock_id and date_str:
                row = conn.execute(
                    "SELECT * FROM margin_data WHERE date = ? AND stock_id = ?",
                    (date_str, stock_id)
                ).fetchone()
                return dict(row) if row else None
            elif date_str:
                rows = conn.execute(
                    "SELECT * FROM margin_data WHERE date = ? ORDER BY stock_id",
                    (date_str,)
                ).fetchall()
                return [dict(r) for r in rows]
            else:
                rows = conn.execute(
                    """SELECT * FROM margin_data
                       WHERE date = (SELECT MAX(date) FROM margin_data)
                       ORDER BY day_trade_ratio DESC"""
                ).fetchall()
                return [dict(r) for r in rows]
        finally:
            conn.close()


# 全域單例
margin_worker = MarginWorker()
