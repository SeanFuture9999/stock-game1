"""
workers/telegram_bot.py - Telegram 通知推送
純用 httpx 呼叫 Telegram Bot API，不需額外套件
功能：
  - 到價提醒觸發時推播
  - 法人資料抓完後推播摘要
  - AI 檢討完成後推播
  - 支援從設定頁面一鍵偵測 Chat ID
"""
import httpx
import traceback
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# 動態 Chat ID（可從設定頁修改）
_chat_id = TELEGRAM_CHAT_ID


class TelegramBot:
    """Telegram 通知機器人"""

    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = _chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.enabled = bool(self.token)

    def set_chat_id(self, chat_id: str):
        """設定 Chat ID"""
        self.chat_id = str(chat_id)
        print(f"[TG] Chat ID 已設定: {self.chat_id}")

    def is_ready(self) -> bool:
        """檢查是否已設定完成"""
        return bool(self.token and self.chat_id)

    # ==========================================
    # 核心：發送訊息
    # ==========================================

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        發送文字訊息到 Telegram
        parse_mode: 'HTML' or 'Markdown'
        """
        if not self.is_ready():
            print("[TG] 未設定完成（缺少 Token 或 Chat ID），跳過推播")
            return False

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True
                    }
                )
                data = resp.json()
                if data.get("ok"):
                    print(f"[TG] 訊息已推送 (長度: {len(text)})")
                    return True
                else:
                    print(f"[TG] 推送失敗: {data.get('description', 'unknown error')}")
                    return False
        except Exception as e:
            print(f"[TG] 推送異常: {e}")
            traceback.print_exc()
            return False

    # ==========================================
    # 偵測 Chat ID（設定頁使用）
    # ==========================================

    def detect_chat_id(self) -> dict:
        """
        從最近的訊息中偵測 Chat ID
        使用者需先對 Bot 發送訊息
        """
        if not self.token:
            return {"success": False, "error": "未設定 Bot Token"}

        try:
            with httpx.Client(timeout=10) as client:
                # 先清除 webhook 避免衝突
                client.post(f"{self.base_url}/deleteWebhook")

                # 取得更新
                resp = client.get(
                    f"{self.base_url}/getUpdates",
                    params={"timeout": 5, "allowed_updates": '["message"]'}
                )
                data = resp.json()

                if not data.get("ok"):
                    return {"success": False, "error": data.get("description", "API 錯誤")}

                results = data.get("result", [])
                if not results:
                    return {
                        "success": False,
                        "error": "沒有收到訊息。請先在 Telegram 對 Bot 發送任意訊息，然後再試一次。"
                    }

                # 取最後一則訊息的 chat_id
                last_msg = results[-1].get("message", {})
                chat = last_msg.get("chat", {})
                chat_id = str(chat.get("id", ""))
                username = chat.get("username", "")
                first_name = chat.get("first_name", "")

                if chat_id:
                    self.set_chat_id(chat_id)
                    return {
                        "success": True,
                        "chat_id": chat_id,
                        "username": username,
                        "name": first_name
                    }
                else:
                    return {"success": False, "error": "無法解析 Chat ID"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # 便捷方法：各場景推播
    # ==========================================

    def notify_alert_triggered(self, stock_id: str, stock_name: str,
                                alert_type: str, target_price: float,
                                current_price: float = 0):
        """到價提醒觸發"""
        type_text = "突破" if alert_type == "above" else "跌破"
        emoji = "📈" if alert_type == "above" else "📉"
        price_info = f"\n現價: {current_price}" if current_price else ""

        text = (
            f"{emoji} <b>到價提醒觸發</b>\n\n"
            f"股票: <b>{stock_id} {stock_name}</b>\n"
            f"類型: {type_text} {target_price}{price_info}\n"
            f"目標價: {target_price}"
        )
        self.send_message(text)

    def notify_institutional_done(self, date_str: str, market_data: dict = None):
        """法人資料抓取完成"""
        text = f"📊 <b>法人籌碼更新完成</b>\n日期: {date_str}\n"

        if market_data:
            text += (
                f"\n三大法人買賣超:\n"
                f"  外資: {market_data.get('foreign_net', 0):+.2f} 億\n"
                f"  投信: {market_data.get('trust_net', 0):+.2f} 億\n"
                f"  自營: {market_data.get('dealer_net', 0):+.2f} 億\n"
                f"  合計: {market_data.get('total_net', 0):+.2f} 億"
            )

        self.send_message(text)

    def notify_ai_review_done(self, date_str: str, review_summary: str = ""):
        """AI 檢討完成"""
        # 截取前 500 字避免 Telegram 4096 字元限制
        summary = review_summary[:500] + "..." if len(review_summary) > 500 else review_summary

        text = (
            f"🤖 <b>AI 每日檢討已生成</b>\n"
            f"日期: {date_str}\n\n"
            f"{summary}\n\n"
            f"完整報告請到戰情室查看"
        )
        self.send_message(text)

    def notify_margin_done(self, date_str: str, count: int = 0):
        """融資融券資料完成"""
        text = (
            f"💳 <b>融資融券資料更新完成</b>\n"
            f"日期: {date_str}\n"
            f"更新股票數: {count} 檔"
        )
        self.send_message(text)

    def send_test(self) -> bool:
        """發送測試訊息"""
        return self.send_message(
            "✅ <b>台股戰情室 Telegram 通知測試</b>\n\n"
            "恭喜！通知功能已設定成功。\n"
            "你將會在以下時機收到推播:\n"
            "  - 到價提醒觸發\n"
            "  - 法人籌碼更新完成 (18:05)\n"
            "  - AI 每日檢討完成 (18:15)\n"
            "  - 融資融券更新完成 (18:10)"
        )


# 全域單例
telegram_bot = TelegramBot()
