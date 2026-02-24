"""
workers/ai_analyzer.py - AI 分析引擎
支援 Gemini（主要）/ 可切換 provider
功能：
  A. 值得關注股票推薦（含獲利空間、週期、停損價）
  B. 每日自動檢討（操作摘要、勝率、情緒、偏離度、明日方案）
  C. 盤後市場總結
"""
import threading
import traceback
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

import google.generativeai as genai
from config import GOOGLE_API_KEY
from database.models import (
    get_trades, get_diary, save_diary, get_watchlist,
    get_portfolio, get_market_institutional, get_institutional,
    get_latest_snapshots
)


class AIAnalyzer:
    """AI 分析引擎"""

    def __init__(self):
        self.provider = "gemini"  # 'gemini' / 'claude' / 'local'
        self.model = None
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.last_review_date = None

    # ==========================================
    # 初始化 AI Model
    # ==========================================

    def init_model(self):
        """初始化 AI 模型"""
        if self.provider == "gemini":
            genai.configure(api_key=GOOGLE_API_KEY)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
            print("[AI] Gemini 2.5 Flash 模型已載入")
        # 預留其他 provider
        # elif self.provider == "claude":
        #     ...
        # elif self.provider == "local":
        #     ...

    def generate(self, prompt: str, max_retries: int = 2) -> str:
        """呼叫 AI 生成回應"""
        if not self.model:
            self.init_model()

        for attempt in range(max_retries + 1):
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"[AI] 生成失敗 (第{attempt+1}次): {e}")
                if attempt == max_retries:
                    return f"[AI 分析暫時無法使用: {e}]"

    # ==========================================
    # A. 值得關注股票推薦
    # ==========================================

    def recommend_stocks(self, market_snapshot: list = None) -> dict:
        """
        推薦值得關注的股票
        回傳：推薦清單 + 獲利空間 + 週期 + 停損價
        """
        # 收集資料
        portfolio = get_portfolio()
        watchlist = get_watchlist()
        hold_ids = [w["stock_id"] for w in watchlist if w["category"] == "hold"]
        watch_ids = [w["stock_id"] for w in watchlist if w["category"] == "watch"]

        # 大盤法人
        market_inst = get_market_institutional()
        market_inst_str = "無資料"
        if market_inst:
            market_inst_str = (
                f"外資:{market_inst['foreign_net']:+.2f}億 "
                f"投信:{market_inst['trust_net']:+.2f}億 "
                f"自營:{market_inst['dealer_net']:+.2f}億"
            )

        # 最新行情
        snapshots = get_latest_snapshots()
        snapshot_str = ""
        if snapshots:
            lines = []
            for s in snapshots:
                lines.append(
                    f"{s['stock_id']} {s['stock_name']} "
                    f"價:{s['price']} 漲跌:{s['change_percent']:+.2f}% "
                    f"量:{s['total_volume']}"
                )
            snapshot_str = "\n".join(lines)

        prompt = f"""你是專業台股分析師。請根據以下市場資料，推薦 2-3 檔值得關注的股票。

## 目前持有
{', '.join(hold_ids) if hold_ids else '無'}

## 目前關注
{', '.join(watch_ids) if watch_ids else '無'}

## 大盤法人動向
{market_inst_str}

## 最新行情快照
{snapshot_str if snapshot_str else '無即時資料'}

## 推薦要求
請推薦 **不在** 我持有和關注清單中的股票。每檔股票請提供：

1. **股票代號與名稱**
2. **目前股價**（最近一個交易日的收盤價，必須是真實數字）
3. **推薦理由**（技術面/基本面/題材/資金面，具體說明）
4. **預估獲利空間**（文字描述，如「短線 5-10% 空間」或「中期 3 個月 15-20%」）
5. **建議觀察週期**（短線 1-2 週 / 波段 1-3 個月 / 中長期 3 個月以上）
6. **目標價位**（具體數字）
7. **建議停損價位**（具體數字，用技術面支撐位設定）
8. **風險提示**

## 格式
請用以下 JSON 格式回覆（純 JSON，不要 markdown）：
{{
  "recommendations": [
    {{
      "stock_id": "代號",
      "stock_name": "名稱",
      "current_price": 目前股價數字,
      "reason": "推薦理由",
      "profit_potential": "獲利空間描述",
      "time_horizon": "觀察週期",
      "stop_loss_price": 停損數字,
      "target_price": 目標數字,
      "risk": "風險提示"
    }}
  ],
  "market_outlook": "整體盤勢觀點（2-3句話）"
}}

**重要：current_price 必須填入該股票最近一個交易日的真實收盤價，不可省略。**

**重要聲明：以上分析僅供參考，不構成任何投資建議。投資有風險，請自行評估。**
"""

        result_text = self.generate(prompt)

        # 嘗試解析 JSON
        import json
        try:
            # 清理可能的 markdown 包裹
            clean = result_text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                clean = clean.rsplit("```", 1)[0]
            result = json.loads(clean)
            result["disclaimer"] = "以上分析僅供參考，不構成任何投資建議。投資有風險，請自行評估。"
            result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return result
        except json.JSONDecodeError:
            return {
                "recommendations": [],
                "market_outlook": result_text,
                "disclaimer": "以上分析僅供參考，不構成任何投資建議。投資有風險，請自行評估。",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "raw_response": True
            }

    # ==========================================
    # B. 每日自動檢討
    # ==========================================

    def generate_daily_review(self, date_str: str = None) -> str:
        """
        生成每日自動檢討報告
        包含：操作摘要、勝率、最大虧損、情緒分析、偏離度、明日方案
        """
        if not date_str:
            date_str = date.today().isoformat()

        # 1. 收集當日交易
        trades = get_trades(date_str=date_str)

        # 2. 持倉狀況
        portfolio = get_portfolio()

        # 3. 法人籌碼
        market_inst = get_market_institutional(date_str)
        stock_inst = get_institutional(date_str=date_str)

        # 4. 計算當日統計
        buy_trades = [t for t in trades if t["action"] == "buy"]
        sell_trades = [t for t in trades if t["action"] == "sell"]
        total_fee = sum(t["fee"] for t in trades)
        total_tax = sum(t["tax"] for t in trades)

        # 5. 計算勝率（賣出交易中獲利的比例）
        # 需要對比 portfolio 的 avg_cost
        portfolio_map = {p["stock_id"]: p for p in portfolio}
        winning_sells = 0
        losing_sells = 0
        max_loss = 0
        max_loss_stock = ""

        for t in sell_trades:
            avg_cost = portfolio_map.get(t["stock_id"], {}).get("avg_cost", 0)
            if avg_cost > 0:
                profit_per_share = t["price"] - avg_cost
                if profit_per_share > 0:
                    winning_sells += 1
                else:
                    losing_sells += 1
                    loss = profit_per_share * t["shares"]
                    if loss < max_loss:
                        max_loss = loss
                        max_loss_stock = f"{t['stock_id']} {t['stock_name']}"

        total_sell_trades = winning_sells + losing_sells
        win_rate = (winning_sells / total_sell_trades * 100) if total_sell_trades > 0 else 0

        # 6. 組裝交易摘要文字
        trade_summary = "今日無交易操作。"
        if trades:
            lines = []
            for t in trades:
                action = "買入" if t["action"] == "buy" else "賣出"
                lines.append(
                    f"- {action} {t['stock_id']} {t['stock_name']} "
                    f"{t['shares']}股 @ {t['price']} "
                    f"(淨額:{t['net_amount']:,.0f})"
                )
            trade_summary = "\n".join(lines)

        # 7. 法人摘要
        inst_summary = "法人資料尚未取得"
        if market_inst:
            inst_summary = (
                f"外資:{market_inst['foreign_net']:+.2f}億 "
                f"投信:{market_inst['trust_net']:+.2f}億 "
                f"自營:{market_inst['dealer_net']:+.2f}億 "
                f"合計:{market_inst['total_net']:+.2f}億"
            )

        # 8. 持倉摘要
        portfolio_lines = []
        total_unrealized = 0
        for p in portfolio:
            if p["total_shares"] > 0:
                portfolio_lines.append(
                    f"- {p['stock_id']} {p['stock_name']} "
                    f"{p['total_shares']}股 均價{p['avg_cost']:.2f}"
                )

        portfolio_summary = "\n".join(portfolio_lines) if portfolio_lines else "目前無持倉"

        # 9. 既有日記（讀取使用者之前寫的筆記）
        existing_diary = get_diary(date_str)
        user_notes = ""
        if existing_diary and existing_diary.get("user_notes"):
            user_notes = f"\n使用者自己的筆記：{existing_diary['user_notes']}"

        # 10. 生成 AI 檢討
        prompt = f"""你是我的個人股市交易教練。請根據以下資料，為我生成今日（{date_str}）的交易檢討報告。

## 今日交易操作
{trade_summary}

## 費用統計
手續費合計：{total_fee:,.0f} 元
交易稅合計：{total_tax:,.0f} 元

## 賣出勝率
今日：{win_rate:.0f}%（{winning_sells}勝 {losing_sells}敗）
最大單筆虧損：{max_loss:,.0f} 元 {max_loss_stock}

## 目前持倉
{portfolio_summary}

## 大盤法人動向
{inst_summary}

## 個股法人籌碼
{chr(10).join([f"- {s['stock_id']} {s['stock_name']}: 外資{s['foreign_net']:+d} 投信{s['trust_net']:+d} 合計{s['total_net']:+d}" for s in (stock_inst or [])[:10]])}
{user_notes}

## 請輸出以下格式的檢討報告

### 今日操作摘要
（用 2-3 句話總結今日的操作邏輯和結果）

### 勝率分析
- 今日勝率：XX%
- 交易成本：手續費 XX + 稅 XX = 共 XX 元

### 操作檢討
（分析每筆交易是否合理，有沒有追高、恐慌賣出、不遵守紀律的情況）

### 情緒評估
（根據交易行為判斷今日情緒狀態：紀律執行/冷靜/衝動/恐慌/貪婪）

### 與計劃偏離度
（如果有前一天的計劃，評估今日是否按計劃執行）

### 法人籌碼解讀
（根據法人資料，分析主力動向對我持股的影響）

### 明日行動方案
（具體的明日操作建議，包含要觀察的指標、價位）

語氣要直接、專業、有建設性。不要客套，直接點出問題。
"""

        review_text = self.generate(prompt)

        # 儲存到資料庫
        save_diary(
            date_str=date_str,
            ai_review=review_text,
            market_summary=inst_summary
        )

        self.last_review_date = date_str
        print(f"[AI] 每日檢討已生成並儲存：{date_str}")
        return review_text

    # ==========================================
    # C. 盤後市場總結（供日記使用）
    # ==========================================

    def generate_market_summary(self, date_str: str = None) -> str:
        """生成盤後市場總結"""
        if not date_str:
            date_str = date.today().isoformat()

        market_inst = get_market_institutional(date_str)
        stock_inst = get_institutional(date_str=date_str)

        if not market_inst:
            return "今日法人資料尚未取得，無法生成市場總結。"

        prompt = f"""請用 3-5 句話簡要總結今日（{date_str}）台股盤勢：

三大法人：外資{market_inst['foreign_net']:+.2f}億 投信{market_inst['trust_net']:+.2f}億 自營{market_inst['dealer_net']:+.2f}億

語氣簡潔專業，重點放在：
1. 法人態度（做多/做空/觀望）
2. 資金流向（哪些族群受青睞）
3. 明日盤勢展望
"""
        return self.generate(prompt)

    # ==========================================
    # 排程任務
    # ==========================================

    def scheduled_daily_review(self):
        """排程：盤後自動生成檢討"""
        today = date.today()
        if today.weekday() >= 5:
            return  # 週末跳過

        if self.last_review_date == today.isoformat():
            return  # 今天已生成過

        print("[AI] ===== 開始生成每日自動檢討 =====")
        try:
            self.generate_daily_review()
        except Exception as e:
            print(f"[AI] 自動檢討生成失敗: {e}")
            traceback.print_exc()

    # ==========================================
    # 啟動 / 停止
    # ==========================================

    def start(self):
        """啟動 AI 引擎"""
        if self.is_running:
            return

        self.init_model()

        # 每日 18:15 自動生成檢討（在法人資料抓完後 10 分鐘）
        self.scheduler.add_job(
            self.scheduled_daily_review,
            trigger="cron",
            hour=18,
            minute=15,
            id="daily_ai_review",
            replace_existing=True
        )

        # 如果啟動時已過 18:15 且今天還沒生成，立即補生成
        now = datetime.now()
        if now.hour >= 18 and now.minute >= 15:
            if self.last_review_date != date.today().isoformat():
                threading.Thread(target=self.scheduled_daily_review, daemon=True).start()

        self.scheduler.start()
        self.is_running = True
        print("[AI Worker] 排程啟動：每日 18:15 自動生成檢討報告")

    def stop(self):
        """停止 AI 引擎"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.is_running = False
        print("[AI Worker] 已停止")


# 全域單例
ai_analyzer = AIAnalyzer()
