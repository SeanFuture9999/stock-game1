"""
workers/alert_manager.py - 到價提醒管理器
盤中每次行情更新時檢查是否觸發提醒
支援：突破/跌破目標價
"""
import threading
import time
from datetime import datetime
from database.models import get_watchlist

import sqlite3
from config import DB_PATH


class AlertManager:
    """到價提醒管理器"""

    def __init__(self):
        self.triggered_alerts = []  # 最近觸發的提醒（前端用 polling 讀取）
        self._lock = threading.Lock()

    # ==========================================
    # CRUD
    # ==========================================

    def add_alert(self, stock_id: str, stock_name: str, alert_type: str, target_price: float):
        """新增到價提醒"""
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """INSERT INTO stock_alerts (stock_id, stock_name, alert_type, target_price)
                   VALUES (?, ?, ?, ?)""",
                (stock_id, stock_name, alert_type, target_price)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[Alert] 新增提醒失敗: {e}")
            return False
        finally:
            conn.close()

    def get_active_alerts(self):
        """取得所有未觸發的提醒"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM stock_alerts WHERE is_triggered = 0 ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all_alerts(self, limit: int = 50):
        """取得所有提醒（含已觸發）"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM stock_alerts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_alert(self, alert_id: int):
        """刪除提醒"""
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("DELETE FROM stock_alerts WHERE id = ?", (alert_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    # ==========================================
    # 檢查觸發
    # ==========================================

    def check_alerts(self, quotes: dict):
        """
        檢查是否有提醒被觸發
        quotes: {stock_id: {price, ...}}
        """
        active_alerts = self.get_active_alerts()
        if not active_alerts:
            return []

        newly_triggered = []
        conn = sqlite3.connect(DB_PATH)

        try:
            for alert in active_alerts:
                stock_id = alert["stock_id"]
                quote = quotes.get(stock_id)
                if not quote:
                    continue

                current_price = quote.get("price", 0)
                if current_price <= 0:
                    continue

                triggered = False

                if alert["alert_type"] == "above" and current_price >= alert["target_price"]:
                    triggered = True
                elif alert["alert_type"] == "below" and current_price <= alert["target_price"]:
                    triggered = True

                if triggered:
                    # 標記為已觸發
                    conn.execute(
                        """UPDATE stock_alerts
                           SET is_triggered = 1, triggered_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (alert["id"],)
                    )

                    alert_msg = {
                        "id": alert["id"],
                        "stock_id": stock_id,
                        "stock_name": alert["stock_name"],
                        "alert_type": alert["alert_type"],
                        "target_price": alert["target_price"],
                        "current_price": current_price,
                        "message": self._format_alert_message(alert, current_price),
                        "triggered_at": datetime.now().strftime("%H:%M:%S")
                    }
                    newly_triggered.append(alert_msg)

            conn.commit()
        finally:
            conn.close()

        # 存到記憶體供前端讀取
        if newly_triggered:
            with self._lock:
                self.triggered_alerts.extend(newly_triggered)
                # 只保留最近 50 條
                self.triggered_alerts = self.triggered_alerts[-50:]

        return newly_triggered

    def get_recent_triggers(self, clear: bool = True):
        """取得最近觸發的提醒（前端 polling 用）"""
        with self._lock:
            triggers = list(self.triggered_alerts)
            if clear:
                self.triggered_alerts = []
        return triggers

    def _format_alert_message(self, alert: dict, current_price: float) -> str:
        """格式化提醒訊息"""
        type_text = "突破" if alert["alert_type"] == "above" else "跌破"
        return (
            f"[到價提醒] {alert['stock_id']} {alert['stock_name']} "
            f"已{type_text} {alert['target_price']} 元！"
            f"（現價 {current_price}）"
        )


# 全域單例
alert_manager = AlertManager()
