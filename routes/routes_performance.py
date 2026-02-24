"""
routes/routes_performance.py - 績效總覽 + 日曆視圖 API
功能：
  - 累計損益曲線
  - 月報表（勝率/總損益/交易次數）
  - 持倉分佈
  - 月曆每日盈虧
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date, datetime, timedelta
from database.models import get_trades, get_portfolio, get_diary
from database.db import get_db_sync

router = APIRouter(prefix="/api/performance", tags=["績效總覽"])


@router.get("/daily-pnl")
async def daily_pnl(months: int = 3):
    """
    取得每日已實現損益（用於累計損益曲線）
    回傳最近 N 個月的每日 P&L
    """
    conn = get_db_sync()
    try:
        start_date = (date.today() - timedelta(days=months * 30)).isoformat()

        rows = conn.execute("""
            SELECT DATE(traded_at) as trade_date,
                   SUM(CASE WHEN action='sell' THEN net_amount ELSE 0 END) as total_sell,
                   SUM(CASE WHEN action='buy' THEN net_amount ELSE 0 END) as total_buy,
                   SUM(fee) as total_fee,
                   SUM(tax) as total_tax,
                   COUNT(*) as trade_count
            FROM trade_log
            WHERE DATE(traded_at) >= ?
            GROUP BY DATE(traded_at)
            ORDER BY trade_date
        """, (start_date,)).fetchall()

        daily_data = []
        cumulative_pnl = 0

        for r in rows:
            row = dict(r)
            # 每日損益 = 賣出淨額 - 買入淨額（簡化計算）
            daily_pnl_val = row["total_sell"] - row["total_buy"]
            cumulative_pnl += daily_pnl_val

            daily_data.append({
                "date": row["trade_date"],
                "daily_pnl": round(daily_pnl_val, 0),
                "cumulative_pnl": round(cumulative_pnl, 0),
                "trade_count": row["trade_count"],
                "fee": round(row["total_fee"], 0),
                "tax": round(row["total_tax"], 0)
            })

        return {"status": "ok", "data": daily_data}
    finally:
        conn.close()


@router.get("/monthly-report")
async def monthly_report(year: Optional[int] = None, month: Optional[int] = None):
    """
    月報表：勝率、總損益、交易次數、手續費、稅
    """
    if not year:
        year = date.today().year
    if not month:
        month = date.today().month

    month_str = f"{year}-{month:02d}"

    conn = get_db_sync()
    try:
        # 當月所有交易
        rows = conn.execute("""
            SELECT * FROM trade_log
            WHERE strftime('%Y-%m', traded_at) = ?
            ORDER BY traded_at
        """, (month_str,)).fetchall()

        trades = [dict(r) for r in rows]

        # 統計
        buy_trades = [t for t in trades if t["action"] == "buy"]
        sell_trades = [t for t in trades if t["action"] == "sell"]
        total_buy = sum(t["net_amount"] for t in buy_trades)
        total_sell = sum(t["net_amount"] for t in sell_trades)
        total_fee = sum(t["fee"] for t in trades)
        total_tax = sum(t["tax"] for t in trades)
        net_pnl = total_sell - total_buy

        # 勝率（賣出交易價格 > 均價成本的比例）
        portfolio_map = {}
        portfolio = get_portfolio()
        for p in portfolio:
            portfolio_map[p["stock_id"]] = p.get("avg_cost", 0)

        winning = 0
        losing = 0
        for t in sell_trades:
            avg_cost = portfolio_map.get(t["stock_id"], 0)
            if avg_cost > 0:
                if t["price"] > avg_cost:
                    winning += 1
                else:
                    losing += 1

        total_decided = winning + losing
        win_rate = (winning / total_decided * 100) if total_decided > 0 else 0

        # 每日交易次數（用於活躍度統計）
        daily_counts = {}
        for t in trades:
            d = t["traded_at"].split(" ")[0] if t["traded_at"] else ""
            if d:
                daily_counts[d] = daily_counts.get(d, 0) + 1

        return {
            "status": "ok",
            "data": {
                "year": year,
                "month": month,
                "total_trades": len(trades),
                "buy_count": len(buy_trades),
                "sell_count": len(sell_trades),
                "total_buy": round(total_buy, 0),
                "total_sell": round(total_sell, 0),
                "net_pnl": round(net_pnl, 0),
                "total_fee": round(total_fee, 0),
                "total_tax": round(total_tax, 0),
                "total_cost": round(total_fee + total_tax, 0),
                "win_rate": round(win_rate, 1),
                "winning_trades": winning,
                "losing_trades": losing,
                "active_days": len(daily_counts),
                "avg_trades_per_day": round(len(trades) / max(len(daily_counts), 1), 1)
            }
        }
    finally:
        conn.close()


@router.get("/portfolio-distribution")
async def portfolio_distribution():
    """
    持倉分佈（圓餅圖資料）
    """
    portfolio = get_portfolio()
    active = [p for p in portfolio if p["total_shares"] > 0]

    total_value = 0
    items = []
    for p in active:
        # 用均價成本 * 持股數估算市值（精確值需要即時價格）
        value = p["avg_cost"] * p["total_shares"]
        total_value += value
        items.append({
            "stock_id": p["stock_id"],
            "stock_name": p.get("stock_name", ""),
            "shares": p["total_shares"],
            "avg_cost": p["avg_cost"],
            "value": round(value, 0)
        })

    # 計算百分比
    for item in items:
        item["percent"] = round(item["value"] / total_value * 100, 1) if total_value > 0 else 0

    # 排序：市值大到小
    items.sort(key=lambda x: x["value"], reverse=True)

    return {
        "status": "ok",
        "data": items,
        "total_value": round(total_value, 0)
    }


@router.get("/calendar")
async def calendar_data(year: Optional[int] = None, month: Optional[int] = None):
    """
    日曆視圖資料：每日盈虧 + 情緒 + 交易次數
    """
    if not year:
        year = date.today().year
    if not month:
        month = date.today().month

    month_str = f"{year}-{month:02d}"

    conn = get_db_sync()
    try:
        # 每日交易損益
        trade_rows = conn.execute("""
            SELECT DATE(traded_at) as trade_date,
                   SUM(CASE WHEN action='sell' THEN net_amount ELSE 0 END) -
                   SUM(CASE WHEN action='buy' THEN net_amount ELSE 0 END) as daily_pnl,
                   COUNT(*) as trade_count,
                   SUM(fee) + SUM(tax) as cost
            FROM trade_log
            WHERE strftime('%Y-%m', traded_at) = ?
            GROUP BY DATE(traded_at)
        """, (month_str,)).fetchall()

        # 每日日記（情緒標記）
        diary_rows = conn.execute("""
            SELECT date, emotion_tag, user_notes, ai_review
            FROM daily_diary
            WHERE strftime('%Y-%m', date) = ?
        """, (month_str,)).fetchall()

        diary_map = {}
        for d in diary_rows:
            dd = dict(d)
            diary_map[dd["date"]] = {
                "emotion_tag": dd.get("emotion_tag", ""),
                "has_notes": bool(dd.get("user_notes")),
                "has_ai_review": bool(dd.get("ai_review"))
            }

        calendar = []
        for r in trade_rows:
            row = dict(r)
            d = row["trade_date"]
            diary_info = diary_map.get(d, {})

            calendar.append({
                "date": d,
                "daily_pnl": round(row["daily_pnl"], 0),
                "trade_count": row["trade_count"],
                "cost": round(row["cost"], 0),
                "emotion_tag": diary_info.get("emotion_tag", ""),
                "has_notes": diary_info.get("has_notes", False),
                "has_ai_review": diary_info.get("has_ai_review", False)
            })

        # 補上有日記但沒交易的日期
        for d, info in diary_map.items():
            if d not in [c["date"] for c in calendar]:
                calendar.append({
                    "date": d,
                    "daily_pnl": 0,
                    "trade_count": 0,
                    "cost": 0,
                    "emotion_tag": info.get("emotion_tag", ""),
                    "has_notes": info.get("has_notes", False),
                    "has_ai_review": info.get("has_ai_review", False)
                })

        # 按日期排序
        calendar.sort(key=lambda x: x["date"])

        return {
            "status": "ok",
            "year": year,
            "month": month,
            "data": calendar
        }
    finally:
        conn.close()


@router.get("/summary")
async def overall_summary():
    """
    總績效摘要（所有時間）
    """
    conn = get_db_sync()
    try:
        # 總已實現損益（從 portfolio_summary）
        row = conn.execute("""
            SELECT COALESCE(SUM(realized_profit), 0) as total_realized
            FROM portfolio_summary
        """).fetchone()
        total_realized = dict(row)["total_realized"]

        # 總交易次數和費用
        row2 = conn.execute("""
            SELECT COUNT(*) as total_trades,
                   COALESCE(SUM(fee), 0) as total_fee,
                   COALESCE(SUM(tax), 0) as total_tax
            FROM trade_log
        """).fetchone()
        stats = dict(row2)

        # 交易天數
        row3 = conn.execute("""
            SELECT COUNT(DISTINCT DATE(traded_at)) as trading_days
            FROM trade_log
        """).fetchone()
        trading_days = dict(row3)["trading_days"]

        # 持倉
        portfolio = get_portfolio()
        active_positions = len([p for p in portfolio if p["total_shares"] > 0])

        return {
            "status": "ok",
            "data": {
                "total_realized_pnl": round(total_realized, 0),
                "total_trades": stats["total_trades"],
                "total_fee": round(stats["total_fee"], 0),
                "total_tax": round(stats["total_tax"], 0),
                "total_cost": round(stats["total_fee"] + stats["total_tax"], 0),
                "trading_days": trading_days,
                "active_positions": active_positions
            }
        }
    finally:
        conn.close()
