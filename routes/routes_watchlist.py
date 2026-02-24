"""
api/routes_watchlist.py - 關注清單 & 持倉管理 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from database.models import (
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    update_watchlist_category, get_portfolio
)
from workers.shioaji_worker import worker

router = APIRouter(prefix="/api/watchlist", tags=["關注清單"])


class AddStockRequest(BaseModel):
    stock_id: str
    category: str = "watch"  # 'hold' or 'watch'
    notes: str = ""


class UpdateCategoryRequest(BaseModel):
    category: str


# ==========================================
# 關注清單
# ==========================================

@router.get("/")
async def list_watchlist(category: Optional[str] = None):
    """取得關注清單（可篩選 hold/watch）"""
    items = get_watchlist(category)

    # 補上即時行情
    cache = worker.get_cache()
    for item in items:
        quote = cache.get(item["stock_id"], {})
        item["price"] = quote.get("price", 0)
        item["change_percent"] = quote.get("change_percent", 0)
        item["volume"] = quote.get("total_volume", 0)
        item["vwap"] = quote.get("vwap", 0)
        item["high"] = quote.get("high", 0)
        item["low"] = quote.get("low", 0)
        item["update_time"] = quote.get("update_time", "")

    return {"data": items, "count": len(items)}


@router.post("/add")
async def add_stock(req: AddStockRequest):
    """新增股票到關注清單"""
    stock_id = req.stock_id.strip()

    if not stock_id:
        raise HTTPException(status_code=400, detail="股票代號不得為空")

    # 驗證代號有效性
    stock_name = ""
    if worker.is_connected:
        if not worker.is_valid_stock(stock_id):
            raise HTTPException(status_code=400, detail=f"無效的股票代號: {stock_id}")
        stock_name = worker.get_stock_name(stock_id)

    success = add_to_watchlist(stock_id, stock_name, req.category, req.notes)
    if not success:
        raise HTTPException(status_code=500, detail="新增失敗")

    return {
        "status": "ok",
        "message": f"已新增 {stock_id} {stock_name} 到{'持有' if req.category == 'hold' else '關注'}清單",
        "stock_name": stock_name
    }


@router.delete("/remove/{stock_id}")
async def remove_stock(stock_id: str):
    """從關注清單移除"""
    success = remove_from_watchlist(stock_id)
    if not success:
        raise HTTPException(status_code=500, detail="移除失敗")
    return {"status": "ok", "message": f"已移除 {stock_id}"}


@router.put("/category/{stock_id}")
async def change_category(stock_id: str, req: UpdateCategoryRequest):
    """切換持有/關注狀態"""
    if req.category not in ("hold", "watch"):
        raise HTTPException(status_code=400, detail="category 必須是 'hold' 或 'watch'")

    success = update_watchlist_category(stock_id, req.category)
    return {
        "status": "ok",
        "message": f"{stock_id} 已切換為{'持有' if req.category == 'hold' else '關注'}"
    }


# ==========================================
# 持倉
# ==========================================

@router.get("/portfolio")
async def list_portfolio():
    """取得持倉摘要（含未實現損益）"""
    portfolio = get_portfolio()
    cache = worker.get_cache()

    for item in portfolio:
        quote = cache.get(item["stock_id"], {})
        current_price = quote.get("price", 0)
        item["current_price"] = current_price
        item["change_percent"] = quote.get("change_percent", 0)
        item["update_time"] = quote.get("update_time", "")

        # 計算未實現損益
        if item["total_shares"] > 0 and current_price > 0:
            item["unrealized_profit"] = round(
                (current_price - item["avg_cost"]) * item["total_shares"], 2
            )
            item["unrealized_percent"] = round(
                (current_price - item["avg_cost"]) / item["avg_cost"] * 100, 2
            ) if item["avg_cost"] > 0 else 0
            item["market_value"] = round(current_price * item["total_shares"], 2)
        else:
            item["unrealized_profit"] = 0
            item["unrealized_percent"] = 0
            item["market_value"] = 0

    # 計算總計
    total_market_value = sum(i["market_value"] for i in portfolio)
    total_unrealized = sum(i["unrealized_profit"] for i in portfolio)
    total_realized = sum(i.get("realized_profit", 0) for i in portfolio)

    return {
        "data": portfolio,
        "summary": {
            "total_market_value": round(total_market_value, 2),
            "total_unrealized_profit": round(total_unrealized, 2),
            "total_realized_profit": round(total_realized, 2),
            "total_profit": round(total_unrealized + total_realized, 2)
        }
    }
