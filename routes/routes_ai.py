"""
routes/routes_ai.py - AI 分析 API 路由
推薦股票 + 每日檢討 + 市場總結 + 推薦回測
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timedelta

from workers.ai_analyzer import ai_analyzer
from workers.shioaji_worker import worker as shioaji_worker
from database.db import get_db_sync

router = APIRouter(prefix="/api/ai", tags=["AI 分析"])


@router.post("/recommend")
async def ai_recommend():
    """AI 推薦值得關注的股票"""
    try:
        result = ai_analyzer.recommend_stocks()

        # 儲存推薦到 DB（供回測用）
        if result.get("recommendations"):
            _save_recommendations(result["recommendations"])

        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 推薦失敗: {e}")


def _save_recommendations(recommendations: list):
    """儲存 AI 推薦紀錄（供回測追蹤）"""
    conn = get_db_sync()
    today = date.today().isoformat()
    try:
        for r in recommendations:
            conn.execute("""
                INSERT INTO ai_recommendations
                (date, stock_id, stock_name, reason, profit_potential,
                 time_horizon, stop_loss_price, target_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                today,
                r.get("stock_id", ""),
                r.get("stock_name", ""),
                r.get("reason", ""),
                r.get("profit_potential", ""),
                r.get("time_horizon", ""),
                r.get("stop_loss_price", 0),
                r.get("target_price", 0)
            ))
        conn.commit()
        print(f"[AI] 已儲存 {len(recommendations)} 筆推薦紀錄")
    except Exception as e:
        print(f"[AI] 儲存推薦失敗: {e}")
    finally:
        conn.close()


@router.post("/review")
async def ai_daily_review(date_str: Optional[str] = None):
    """手動觸發生成每日檢討"""
    if not date_str:
        date_str = date.today().isoformat()
    try:
        review = ai_analyzer.generate_daily_review(date_str)
        return {"status": "ok", "date": date_str, "review": review}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成檢討失敗: {e}")


@router.post("/market-summary")
async def ai_market_summary(date_str: Optional[str] = None):
    """生成盤後市場總結"""
    if not date_str:
        date_str = date.today().isoformat()
    try:
        summary = ai_analyzer.generate_market_summary(date_str)
        return {"status": "ok", "date": date_str, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成市場總結失敗: {e}")


# ==========================================
# AI 推薦回測
# ==========================================

@router.get("/backtest")
async def ai_backtest(days: int = 30):
    """
    AI 推薦回測：追蹤歷史推薦的實際表現
    比對推薦時的目標價/停損價 vs 現在的實際結果
    """
    conn = get_db_sync()
    try:
        start_date = (date.today() - timedelta(days=days)).isoformat()

        rows = conn.execute("""
            SELECT * FROM ai_recommendations
            WHERE date >= ?
            ORDER BY date DESC, stock_id
        """, (start_date,)).fetchall()

        recommendations = [dict(r) for r in rows]

        # 取得最新快取行情
        cache = shioaji_worker.cache if shioaji_worker else {}

        # 計算每筆推薦的結果
        hit_target = 0
        hit_stoploss = 0
        pending = 0
        expired = 0
        total = len(recommendations)

        results = []
        for rec in recommendations:
            stock_id = rec["stock_id"]
            target = rec.get("target_price", 0) or 0
            stoploss = rec.get("stop_loss_price", 0) or 0
            rec_date = rec.get("date", "")

            # 取得目前價格（從快取或 DB）
            current_price = 0
            if stock_id in cache:
                current_price = cache[stock_id].get("price", 0)

            # 判斷推薦結果
            status = "pending"
            actual_result = rec.get("actual_result", "")

            if actual_result:
                # 已有手動/自動標記
                status = actual_result
            elif current_price > 0 and target > 0 and current_price >= target:
                status = "hit_target"
                hit_target += 1
            elif current_price > 0 and stoploss > 0 and current_price <= stoploss:
                status = "hit_stoploss"
                hit_stoploss += 1
            else:
                # 檢查是否過期（超過時間週期）
                time_horizon = rec.get("time_horizon", "")
                days_passed = (date.today() - date.fromisoformat(rec_date)).days if rec_date else 0

                if "短線" in time_horizon and days_passed > 14:
                    status = "expired"
                    expired += 1
                elif "波段" in time_horizon and days_passed > 90:
                    status = "expired"
                    expired += 1
                elif days_passed > 180:
                    status = "expired"
                    expired += 1
                else:
                    pending += 1

            # 計算報酬率（如果有現價和推薦日的 current_price）
            rec_price = 0
            # 嘗試從 reason 或其他欄位推斷推薦時的價格
            # 或直接用 ai_recommendations 表中可能存的 current_price
            # 目前簡化：用 target 和 stoploss 推算中位數
            if target > 0 and stoploss > 0:
                rec_price = (target + stoploss) / 2  # 粗估推薦時價格
            pnl_percent = 0
            if rec_price > 0 and current_price > 0:
                pnl_percent = round((current_price - rec_price) / rec_price * 100, 1)

            results.append({
                "id": rec.get("id"),
                "date": rec_date,
                "stock_id": stock_id,
                "stock_name": rec.get("stock_name", ""),
                "target_price": target,
                "stop_loss_price": stoploss,
                "current_price": current_price,
                "status": status,
                "pnl_percent": pnl_percent,
                "time_horizon": rec.get("time_horizon", ""),
                "reason": rec.get("reason", "")[:50]  # 截短
            })

        # 統計
        decided = hit_target + hit_stoploss
        accuracy = round(hit_target / decided * 100, 1) if decided > 0 else 0

        return {
            "status": "ok",
            "summary": {
                "total": total,
                "hit_target": hit_target,
                "hit_stoploss": hit_stoploss,
                "pending": pending,
                "expired": expired,
                "accuracy": accuracy
            },
            "data": results
        }
    finally:
        conn.close()


@router.post("/backtest/update/{rec_id}")
async def update_backtest_result(rec_id: int, result: str):
    """手動更新推薦結果（hit_target / hit_stoploss / expired）"""
    allowed = ["hit_target", "hit_stoploss", "expired", "pending"]
    if result not in allowed:
        raise HTTPException(status_code=400, detail=f"結果必須是: {', '.join(allowed)}")

    conn = get_db_sync()
    try:
        conn.execute(
            "UPDATE ai_recommendations SET actual_result = ? WHERE id = ?",
            (result, rec_id)
        )
        conn.commit()
        return {"status": "ok", "message": "已更新"}
    finally:
        conn.close()


@router.get("/status")
async def ai_status():
    """AI 引擎狀態"""
    return {
        "provider": ai_analyzer.provider,
        "is_running": ai_analyzer.is_running,
        "last_review_date": ai_analyzer.last_review_date
    }
