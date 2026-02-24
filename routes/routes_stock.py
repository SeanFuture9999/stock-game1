"""
api/routes_stock.py - 即時行情 API 路由
"""
from fastapi import APIRouter, HTTPException
from workers.shioaji_worker import worker

router = APIRouter(prefix="/api/stock", tags=["行情"])


@router.get("/quotes")
async def get_all_quotes():
    """取得所有關注股票的最新行情（從快取讀取）"""
    cache = worker.get_cache()
    if not cache:
        return {"data": [], "status": "no_data", "message": "尚無行情資料，可能尚未開盤或 Worker 未啟動"}

    return {
        "data": list(cache.values()),
        "status": "ok",
        "last_update": worker.last_update.strftime("%H:%M:%S") if worker.last_update else None,
        "count": len(cache)
    }


@router.get("/quote/{stock_id}")
async def get_single_quote(stock_id: str):
    """取得單一股票的最新行情"""
    data = worker.get_stock_cache(stock_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"找不到 {stock_id} 的行情資料")
    return {"data": data, "status": "ok"}


@router.get("/status")
async def get_worker_status():
    """取得 Worker 狀態"""
    from workers.shioaji_worker import worker as w
    return {
        "is_connected": w.is_connected,
        "is_running": w.is_running,
        "is_trading_time": w.is_trading_time(),
        "session": w.get_session_name(),
        "cached_stocks": len(w.cache),
        "last_update": w.last_update.strftime("%H:%M:%S") if w.last_update else None
    }


@router.post("/refresh")
async def force_refresh():
    """強制刷新行情（手動觸發）"""
    from database.models import get_watchlist
    watchlist = get_watchlist()
    stock_ids = [w["stock_id"] for w in watchlist]

    if not stock_ids:
        return {"status": "no_stocks", "message": "關注清單為空"}

    results = worker.fetch_snapshots(stock_ids)
    return {
        "status": "ok",
        "updated": len(results),
        "data": list(results.values())
    }


@router.get("/validate/{stock_id}")
async def validate_stock(stock_id: str):
    """檢查股票代號是否有效"""
    is_valid = worker.is_valid_stock(stock_id)
    name = worker.get_stock_name(stock_id) if is_valid else ""
    return {
        "stock_id": stock_id,
        "is_valid": is_valid,
        "stock_name": name
    }
