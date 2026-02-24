"""
database/models.py - 資料庫 CRUD 操作
提供各模組統一的資料存取介面
"""
import sqlite3
from datetime import datetime, date
from typing import Optional
from config import DB_PATH, BROKER_FEE_RATE, BROKER_FEE_DISCOUNT, TAX_RATE_STOCK, TAX_RATE_ETF


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ==========================================
# Watchlist CRUD
# ==========================================

def get_watchlist(category: Optional[str] = None):
    """取得關注清單，可篩選 hold/watch"""
    conn = _get_conn()
    try:
        if category:
            rows = conn.execute(
                "SELECT * FROM watchlist WHERE category = ? ORDER BY created_at",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM watchlist ORDER BY category DESC, created_at"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_to_watchlist(stock_id: str, stock_name: str = "", category: str = "watch", notes: str = ""):
    """新增股票到關注清單"""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO watchlist (stock_id, stock_name, category, notes)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(stock_id) DO UPDATE SET
                   category = excluded.category,
                   stock_name = excluded.stock_name,
                   notes = excluded.notes,
                   updated_at = CURRENT_TIMESTAMP""",
            (stock_id, stock_name, category, notes)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] 新增 watchlist 失敗: {e}")
        return False
    finally:
        conn.close()


def remove_from_watchlist(stock_id: str):
    """從關注清單移除"""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM watchlist WHERE stock_id = ?", (stock_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def update_watchlist_category(stock_id: str, category: str):
    """切換持有/關注狀態"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE watchlist SET category = ?, updated_at = CURRENT_TIMESTAMP WHERE stock_id = ?",
            (category, stock_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ==========================================
# Portfolio (持倉) CRUD
# ==========================================

def get_portfolio():
    """取得所有持倉"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT p.*, w.notes FROM portfolio_summary p
               LEFT JOIN watchlist w ON p.stock_id = w.stock_id
               ORDER BY p.stock_id"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_portfolio_after_trade(stock_id: str, stock_name: str, action: str, shares: int, price: float, net_amount: float):
    """
    交易後自動更新持倉摘要
    買入：重新計算加權平均成本
    賣出：計算已實現損益，更新剩餘持股
    """
    conn = _get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM portfolio_summary WHERE stock_id = ?", (stock_id,)
        ).fetchone()

        if action == "buy":
            if existing:
                old_shares = existing["total_shares"]
                old_cost = existing["avg_cost"]
                new_total_shares = old_shares + shares
                # 加權平均成本 = (舊成本×舊股數 + 新淨額) / 新總股數
                new_avg_cost = (old_cost * old_shares + net_amount) / new_total_shares if new_total_shares > 0 else 0
                conn.execute(
                    """UPDATE portfolio_summary
                       SET total_shares = ?, avg_cost = ?, stock_name = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE stock_id = ?""",
                    (new_total_shares, round(new_avg_cost, 4), stock_name, stock_id)
                )
            else:
                avg_cost = net_amount / shares if shares > 0 else price
                conn.execute(
                    """INSERT INTO portfolio_summary (stock_id, stock_name, total_shares, avg_cost)
                       VALUES (?, ?, ?, ?)""",
                    (stock_id, stock_name, shares, round(avg_cost, 4))
                )
            # 確保在 watchlist 中標記為持有
            add_to_watchlist(stock_id, stock_name, "hold")

        elif action == "sell":
            if existing:
                old_shares = existing["total_shares"]
                old_cost = existing["avg_cost"]
                sell_shares = min(shares, old_shares)
                # 已實現損益 = 賣出淨額 - (均價成本 × 賣出股數)
                realized = net_amount - (old_cost * sell_shares)
                new_total = old_shares - sell_shares
                old_realized = existing["realized_profit"] or 0

                if new_total <= 0:
                    # 全部賣出，清空持倉但保留紀錄
                    conn.execute(
                        """UPDATE portfolio_summary
                           SET total_shares = 0, realized_profit = ?, updated_at = CURRENT_TIMESTAMP
                           WHERE stock_id = ?""",
                        (round(old_realized + realized, 2), stock_id)
                    )
                    # 從持有改為關注
                    update_watchlist_category(stock_id, "watch")
                else:
                    conn.execute(
                        """UPDATE portfolio_summary
                           SET total_shares = ?, realized_profit = ?, updated_at = CURRENT_TIMESTAMP
                           WHERE stock_id = ?""",
                        (new_total, round(old_realized + realized, 2), stock_id)
                    )

        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] 更新持倉失敗: {e}")
        return False
    finally:
        conn.close()


# ==========================================
# Trade Log CRUD
# ==========================================

def calculate_fees(action: str, shares: int, price: float, stock_id: str = ""):
    """
    計算手續費和交易稅
    手續費 = 成交金額 × 0.1425% × 折數
    交易稅 = 賣出金額 × 0.3%（ETF: 0.1%）
    """
    total_amount = shares * price
    fee = round(total_amount * BROKER_FEE_RATE * BROKER_FEE_DISCOUNT)
    fee = max(fee, 1)  # 最低手續費 1 元（零股也適用）

    tax = 0
    if action == "sell":
        # 判斷是否為 ETF（代號以 00 開頭）
        is_etf = stock_id.startswith("00")
        tax_rate = TAX_RATE_ETF if is_etf else TAX_RATE_STOCK
        tax = round(total_amount * tax_rate)

    if action == "buy":
        net_amount = total_amount + fee
    else:
        net_amount = total_amount - fee - tax

    return {
        "total_amount": round(total_amount, 2),
        "fee": fee,
        "tax": tax,
        "net_amount": round(net_amount, 2)
    }


def add_trade(stock_id: str, stock_name: str, action: str, shares: int, price: float,
              is_odd_lot: bool = False, note: str = "", traded_at: str = ""):
    """
    新增交易紀錄，自動計算手續費和稅，並更新持倉
    """
    fees = calculate_fees(action, shares, price, stock_id)

    conn = _get_conn()
    try:
        trade_time = traded_at if traded_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO trade_log
               (stock_id, stock_name, action, shares, price, total_amount, fee, tax, net_amount, is_odd_lot, note, traded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (stock_id, stock_name, action, shares, price,
             fees["total_amount"], fees["fee"], fees["tax"], fees["net_amount"],
             1 if is_odd_lot else 0, note, trade_time)
        )
        conn.commit()
    finally:
        conn.close()

    # 更新持倉
    update_portfolio_after_trade(stock_id, stock_name, action, shares, price, fees["net_amount"])
    return fees


def get_trades(date_str: Optional[str] = None, stock_id: Optional[str] = None):
    """查詢交易紀錄"""
    conn = _get_conn()
    try:
        query = "SELECT * FROM trade_log WHERE 1=1"
        params = []

        if date_str:
            query += " AND DATE(traded_at) = ?"
            params.append(date_str)
        if stock_id:
            query += " AND stock_id = ?"
            params.append(stock_id)

        query += " ORDER BY traded_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ==========================================
# Daily Diary CRUD
# ==========================================

def get_diary(date_str: Optional[str] = None):
    """取得日記，若無指定日期則取今日"""
    if not date_str:
        date_str = date.today().isoformat()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM daily_diary WHERE date = ?", (date_str,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_diary(date_str: str, ai_review: str = "", user_notes: str = "",
               reminders: str = "", market_summary: str = "",
               emotion_tag: str = "", tomorrow_plan: str = ""):
    """儲存或更新日記"""
    conn = _get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM daily_diary WHERE date = ?", (date_str,)
        ).fetchone()

        if existing:
            # 只更新有值的欄位
            updates = []
            params = []
            if ai_review:
                updates.append("ai_review = ?")
                params.append(ai_review)
            if user_notes:
                updates.append("user_notes = ?")
                params.append(user_notes)
            if reminders:
                updates.append("reminders = ?")
                params.append(reminders)
            if market_summary:
                updates.append("market_summary = ?")
                params.append(market_summary)
            if emotion_tag:
                updates.append("emotion_tag = ?")
                params.append(emotion_tag)
            if tomorrow_plan:
                updates.append("tomorrow_plan = ?")
                params.append(tomorrow_plan)

            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                query = f"UPDATE daily_diary SET {', '.join(updates)} WHERE date = ?"
                params.append(date_str)
                conn.execute(query, params)
        else:
            conn.execute(
                """INSERT INTO daily_diary (date, ai_review, user_notes, reminders, market_summary, emotion_tag, tomorrow_plan)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (date_str, ai_review, user_notes, reminders, market_summary, emotion_tag, tomorrow_plan)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] 儲存日記失敗: {e}")
        return False
    finally:
        conn.close()


# ==========================================
# Institutional Data CRUD
# ==========================================

def save_market_institutional(date_str: str, foreign_net: float, trust_net: float, dealer_net: float):
    """儲存大盤三大法人"""
    conn = _get_conn()
    try:
        total_net = foreign_net + trust_net + dealer_net
        conn.execute(
            """INSERT INTO market_institutional (date, foreign_net, trust_net, dealer_net, total_net)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   foreign_net = excluded.foreign_net,
                   trust_net = excluded.trust_net,
                   dealer_net = excluded.dealer_net,
                   total_net = excluded.total_net,
                   fetched_at = CURRENT_TIMESTAMP""",
            (date_str, foreign_net, trust_net, dealer_net, total_net)
        )
        conn.commit()
    finally:
        conn.close()


def save_stock_institutional(date_str: str, stock_id: str, stock_name: str,
                             foreign_buy: int, foreign_sell: int,
                             trust_buy: int, trust_sell: int,
                             dealer_buy: int, dealer_sell: int):
    """儲存個股法人籌碼"""
    conn = _get_conn()
    try:
        foreign_net = foreign_buy - foreign_sell
        trust_net = trust_buy - trust_sell
        dealer_net = dealer_buy - dealer_sell
        total_net = foreign_net + trust_net + dealer_net

        conn.execute(
            """INSERT INTO institutional_data
               (date, stock_id, stock_name, foreign_buy, foreign_sell, foreign_net,
                trust_buy, trust_sell, trust_net, dealer_buy, dealer_sell, dealer_net, total_net)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date, stock_id) DO UPDATE SET
                   foreign_buy=excluded.foreign_buy, foreign_sell=excluded.foreign_sell,
                   foreign_net=excluded.foreign_net, trust_buy=excluded.trust_buy,
                   trust_sell=excluded.trust_sell, trust_net=excluded.trust_net,
                   dealer_buy=excluded.dealer_buy, dealer_sell=excluded.dealer_sell,
                   dealer_net=excluded.dealer_net, total_net=excluded.total_net,
                   fetched_at=CURRENT_TIMESTAMP""",
            (date_str, stock_id, stock_name,
             foreign_buy, foreign_sell, foreign_net,
             trust_buy, trust_sell, trust_net,
             dealer_buy, dealer_sell, dealer_net, total_net)
        )
        conn.commit()
    finally:
        conn.close()


def get_institutional(date_str: Optional[str] = None, stock_id: Optional[str] = None):
    """查詢法人籌碼"""
    conn = _get_conn()
    try:
        if stock_id and date_str:
            row = conn.execute(
                "SELECT * FROM institutional_data WHERE date = ? AND stock_id = ?",
                (date_str, stock_id)
            ).fetchone()
            return dict(row) if row else None
        elif date_str:
            rows = conn.execute(
                "SELECT * FROM institutional_data WHERE date = ? ORDER BY ABS(total_net) DESC",
                (date_str,)
            ).fetchall()
            return [dict(r) for r in rows]
        else:
            # 取最近一天
            rows = conn.execute(
                """SELECT * FROM institutional_data
                   WHERE date = (SELECT MAX(date) FROM institutional_data)
                   ORDER BY ABS(total_net) DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


def get_market_institutional(date_str: Optional[str] = None):
    """查詢大盤法人"""
    conn = _get_conn()
    try:
        if date_str:
            row = conn.execute(
                "SELECT * FROM market_institutional WHERE date = ?", (date_str,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM market_institutional ORDER BY date DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ==========================================
# Snapshots CRUD
# ==========================================

def save_snapshot(stock_id: str, stock_name: str, data: dict):
    """儲存行情快照"""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO stock_snapshots
               (stock_id, stock_name, price, change_price, change_percent,
                volume, total_volume, amount, high, low, open, close,
                buy_price, sell_price, vwap)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (stock_id, stock_name,
             data.get("price", 0), data.get("change_price", 0), data.get("change_percent", 0),
             data.get("volume", 0), data.get("total_volume", 0), data.get("amount", 0),
             data.get("high", 0), data.get("low", 0), data.get("open", 0), data.get("close", 0),
             data.get("buy_price", 0), data.get("sell_price", 0), data.get("vwap", 0))
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_snapshots():
    """取得所有股票的最新快照"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT s.* FROM stock_snapshots s
               INNER JOIN (
                   SELECT stock_id, MAX(snapshot_at) as max_time
                   FROM stock_snapshots
                   GROUP BY stock_id
               ) latest ON s.stock_id = latest.stock_id AND s.snapshot_at = latest.max_time
               ORDER BY s.stock_id"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
