"""
routes/routes_margin.py - 融資融券 API 路由
"""
from fastapi import APIRouter
from typing import Optional

from workers.margin_worker import margin_worker

router = APIRouter(prefix="/api/margin", tags=["融資融券"])


@router.get("/")
async def get_margin(date_str: Optional[str] = None):
    """查詢融資融券資料"""
    data = margin_worker.get_margin_data(date_str=date_str)
    if not data:
        return {"data": [], "status": "no_data", "message": "尚無融資融券資料"}
    return {"data": data, "status": "ok", "count": len(data)}


@router.get("/stock/{stock_id}")
async def get_stock_margin(stock_id: str, date_str: Optional[str] = None):
    """查詢個股融資融券"""
    from datetime import date
    if not date_str:
        date_str = date.today().isoformat()
    data = margin_worker.get_margin_data(date_str=date_str, stock_id=stock_id)
    return {"data": data, "status": "ok" if data else "no_data"}


@router.post("/fetch")
async def manual_fetch_margin(date_str: Optional[str] = None):
    """手動觸發抓取融資融券"""
    results = margin_worker.fetch_margin_data(date_str)
    return {"status": "ok", "count": len(results), "data": results}


@router.get("/status")
async def margin_status():
    """Worker 狀態"""
    return {
        "last_fetch_date": margin_worker.last_fetch_date,
        "last_fetch_status": margin_worker.last_fetch_status
    }
