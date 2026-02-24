"""
api/routes_diary.py - 每日日記 & 檢討 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date

from database.models import get_diary, save_diary, get_trades

router = APIRouter(prefix="/api/diary", tags=["每日日記"])


class DiaryUpdateRequest(BaseModel):
    user_notes: str = ""
    reminders: str = ""
    emotion_tag: str = ""
    tomorrow_plan: str = ""


class DiaryAIRequest(BaseModel):
    date_str: str = ""


@router.get("/")
async def get_today_diary(date_str: Optional[str] = None):
    """取得指定日期的日記（預設今日）"""
    if not date_str:
        date_str = date.today().isoformat()

    diary = get_diary(date_str)

    # 取得當日交易紀錄
    trades = get_trades(date_str=date_str)

    return {
        "data": diary,
        "trades": trades,
        "date": date_str,
        "has_diary": diary is not None
    }


@router.post("/save")
async def save_today_diary(req: DiaryUpdateRequest, date_str: Optional[str] = None):
    """儲存/更新日記（使用者增補）"""
    if not date_str:
        date_str = date.today().isoformat()

    success = save_diary(
        date_str=date_str,
        user_notes=req.user_notes,
        reminders=req.reminders,
        emotion_tag=req.emotion_tag,
        tomorrow_plan=req.tomorrow_plan
    )

    if not success:
        raise HTTPException(status_code=500, detail="儲存日記失敗")

    return {"status": "ok", "message": f"日記已儲存 ({date_str})"}


@router.get("/list")
async def list_diaries(limit: int = 30):
    """列出最近的日記"""
    import sqlite3
    from config import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM daily_diary ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
        return {"data": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()
