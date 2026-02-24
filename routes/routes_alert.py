"""
routes/routes_alert.py - 到價提醒 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from workers.alert_manager import alert_manager
from workers.shioaji_worker import worker

router = APIRouter(prefix="/api/alert", tags=["到價提醒"])


class AddAlertRequest(BaseModel):
    stock_id: str
    alert_type: str  # 'above' = 突破, 'below' = 跌破
    target_price: float


@router.post("/add")
async def add_alert(req: AddAlertRequest):
    """新增到價提醒"""
    if req.alert_type not in ("above", "below"):
        raise HTTPException(status_code=400, detail="alert_type 必須是 'above' 或 'below'")
    if req.target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price 必須大於 0")

    stock_name = worker.get_stock_name(req.stock_id) if worker.is_connected else ""
    success = alert_manager.add_alert(req.stock_id, stock_name, req.alert_type, req.target_price)

    if not success:
        raise HTTPException(status_code=500, detail="新增提醒失敗")

    type_text = "突破" if req.alert_type == "above" else "跌破"
    return {
        "status": "ok",
        "message": f"已設定：{req.stock_id} {stock_name} {type_text} {req.target_price} 時提醒"
    }


@router.get("/list")
async def list_alerts():
    """取得所有提醒"""
    alerts = alert_manager.get_all_alerts()
    active = [a for a in alerts if not a["is_triggered"]]
    triggered = [a for a in alerts if a["is_triggered"]]
    return {
        "data": alerts,
        "active_count": len(active),
        "triggered_count": len(triggered)
    }


@router.get("/active")
async def active_alerts():
    """取得未觸發的提醒"""
    return {"data": alert_manager.get_active_alerts()}


@router.delete("/delete/{alert_id}")
async def delete_alert(alert_id: int):
    """刪除提醒"""
    success = alert_manager.delete_alert(alert_id)
    if not success:
        raise HTTPException(status_code=500, detail="刪除失敗")
    return {"status": "ok", "message": f"提醒 #{alert_id} 已刪除"}


@router.get("/triggered")
async def get_triggered():
    """取得最近觸發的提醒（前端 polling，讀完清除）"""
    triggers = alert_manager.get_recent_triggers(clear=True)
    return {"data": triggers, "count": len(triggers)}


@router.post("/check")
async def manual_check():
    """手動檢查所有提醒是否觸發"""
    quotes = worker.get_cache()
    triggers = alert_manager.check_alerts(quotes)
    return {
        "status": "ok",
        "triggered": triggers,
        "count": len(triggers)
    }
