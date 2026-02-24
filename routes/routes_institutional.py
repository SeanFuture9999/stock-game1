"""
api/routes_institutional.py - 法人籌碼 API 路由
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import date

from database.models import get_institutional, get_market_institutional
from workers.institutional_worker import institutional_worker

router = APIRouter(prefix="/api/institutional", tags=["法人籌碼"])


@router.get("/market")
async def market_institutional(date_str: Optional[str] = None):
    """查詢大盤三大法人買賣超"""
    data = get_market_institutional(date_str)
    if not data:
        return {"data": None, "status": "no_data", "message": "尚無法人資料，請等待盤後 18:05 自動抓取"}
    return {"data": data, "status": "ok"}


@router.get("/stocks")
async def stock_institutional(date_str: Optional[str] = None):
    """查詢所有關注股票的法人籌碼"""
    data = get_institutional(date_str=date_str)
    if not data:
        return {"data": [], "status": "no_data"}
    return {"data": data, "status": "ok", "count": len(data)}


@router.get("/stock/{stock_id}")
async def single_stock_institutional(stock_id: str, date_str: Optional[str] = None):
    """查詢單一股票的法人籌碼"""
    if not date_str:
        date_str = date.today().isoformat()
    data = get_institutional(date_str=date_str, stock_id=stock_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"找不到 {stock_id} 在 {date_str} 的法人資料")
    return {"data": data, "status": "ok"}


@router.post("/fetch")
async def manual_fetch_institutional(date_str: Optional[str] = None):
    """手動觸發抓取法人資料"""
    result = institutional_worker.manual_fetch(date_str)
    return {"status": "ok", "result": result}


@router.get("/status")
async def institutional_status():
    """查詢法人 Worker 狀態"""
    return {
        "is_running": institutional_worker.is_running,
        "last_fetch_date": institutional_worker.last_fetch_date,
        "last_fetch_status": institutional_worker.last_fetch_status
    }
