"""
routes/routes_tdcc.py - 集保大戶資料 API
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from workers.tdcc_worker import tdcc_worker
from database.models import get_watchlist

router = APIRouter(prefix="/api/tdcc", tags=["集保大戶"])


@router.get("/")
async def get_tdcc_list():
    """取得所有關注股票的集保摘要"""
    watchlist = get_watchlist()
    stock_ids = [w["stock_id"] for w in watchlist]

    results = []
    for stock_id in stock_ids:
        summary = tdcc_worker.get_tdcc_summary(stock_id)
        if summary.get("summary"):
            results.append(summary)

    return {"status": "ok", "data": results}


@router.get("/stock/{stock_id}")
async def get_tdcc_stock(stock_id: str):
    """取得單一股票的集保分級明細"""
    data = tdcc_worker.get_tdcc_summary(stock_id)
    return {"status": "ok", "data": data}


@router.post("/fetch")
async def fetch_tdcc():
    """手動抓取集保資料（所有關注股票）"""
    watchlist = get_watchlist()
    stock_ids = [w["stock_id"] for w in watchlist]

    if not stock_ids:
        raise HTTPException(status_code=400, detail="關注清單為空")

    try:
        count = tdcc_worker.fetch_and_save(stock_ids)
        return {
            "status": "ok",
            "message": f"已抓取 {count} 筆集保資料",
            "count": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抓取失敗: {e}")


@router.get("/status")
async def tdcc_status():
    """集保資料狀態"""
    return {
        "last_fetch_date": tdcc_worker.last_fetch_date
    }
