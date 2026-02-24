"""
api/routes_trade.py - 交易紀錄 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date

from database.models import add_trade, get_trades, calculate_fees
from workers.shioaji_worker import worker

router = APIRouter(prefix="/api/trade", tags=["交易紀錄"])


class TradeRequest(BaseModel):
    stock_id: str
    action: str           # 'buy' or 'sell'
    shares: int
    price: float
    is_odd_lot: bool = False
    note: str = ""
    traded_at: str = ""   # 可指定時間，空字串=現在


class FeeCalcRequest(BaseModel):
    stock_id: str = ""
    action: str
    shares: int
    price: float


@router.post("/add")
async def record_trade(req: TradeRequest):
    """記錄一筆交易"""
    if req.action not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="action 必須是 'buy' 或 'sell'")
    if req.shares <= 0:
        raise HTTPException(status_code=400, detail="股數必須大於 0")
    if req.price <= 0:
        raise HTTPException(status_code=400, detail="價格必須大於 0")

    # 取得股票名稱
    stock_name = worker.get_stock_name(req.stock_id) if worker.is_connected else ""

    fees = add_trade(
        stock_id=req.stock_id,
        stock_name=stock_name,
        action=req.action,
        shares=req.shares,
        price=req.price,
        is_odd_lot=req.is_odd_lot,
        note=req.note,
        traded_at=req.traded_at
    )

    action_text = "買入" if req.action == "buy" else "賣出"
    lot_text = "（零股）" if req.is_odd_lot else ""

    return {
        "status": "ok",
        "message": f"已記錄 {action_text} {req.stock_id} {stock_name} {req.shares}股{lot_text} @ {req.price}",
        "fees": fees,
        "stock_name": stock_name
    }


@router.get("/list")
async def list_trades(date_str: Optional[str] = None, stock_id: Optional[str] = None):
    """查詢交易紀錄"""
    if not date_str:
        date_str = date.today().isoformat()

    trades = get_trades(date_str=date_str, stock_id=stock_id)

    # 計算當日統計
    total_buy = sum(t["net_amount"] for t in trades if t["action"] == "buy")
    total_sell = sum(t["net_amount"] for t in trades if t["action"] == "sell")
    total_fee = sum(t["fee"] for t in trades)
    total_tax = sum(t["tax"] for t in trades)

    return {
        "data": trades,
        "count": len(trades),
        "summary": {
            "total_buy": round(total_buy, 2),
            "total_sell": round(total_sell, 2),
            "total_fee": round(total_fee, 2),
            "total_tax": round(total_tax, 2),
            "net_cashflow": round(total_sell - total_buy, 2)
        }
    }


@router.post("/calc-fees")
async def calc_fees(req: FeeCalcRequest):
    """試算手續費和稅"""
    fees = calculate_fees(req.action, req.shares, req.price, req.stock_id)
    return {"data": fees}


@router.get("/history")
async def trade_history(stock_id: Optional[str] = None, limit: int = 50):
    """查詢歷史交易紀錄（不限日期）"""
    trades = get_trades(stock_id=stock_id)
    return {"data": trades[:limit], "count": len(trades)}
