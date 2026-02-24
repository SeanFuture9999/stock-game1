"""
workers/institutional_worker.py - 法人籌碼自動排程 Worker
每日 18:05 自動從 TWSE/TPEx 抓取三大法人買賣超
"""
import httpx
import time
import threading
import traceback
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

from database.models import (
    save_market_institutional,
    save_stock_institutional,
    get_watchlist
)


class InstitutionalWorker:
    """法人籌碼自動抓取引擎"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.last_fetch_date = None
        self.last_fetch_status = "idle"

    # ==========================================
    # TWSE API 抓取 - 大盤三大法人
    # ==========================================

    def fetch_market_institutional(self, date_str: str = None):
        """
        抓取大盤三大法人買賣金額
        API: https://www.twse.com.tw/fund/BFI82U?response=json&date=YYYYMMDD
        """
        if not date_str:
            date_str = date.today().strftime("%Y%m%d")
        else:
            # 統一格式為 YYYYMMDD
            date_str = date_str.replace("-", "")

        url = f"https://www.twse.com.tw/fund/BFI82U?response=json&date={date_str}"

        try:
            print(f"[Institutional] 抓取大盤法人資料: {date_str}")
            resp = httpx.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            data = resp.json()

            if data.get("stat") != "OK" or not data.get("data"):
                print(f"[Institutional] 大盤法人資料尚未公布或無資料: {date_str}")
                return None

            # 解析資料
            # TWSE BFI82U 固定格式（每列 = [名稱, 買進金額, 賣出金額, 買賣差額]）：
            # Row 0: 自營商(自行買賣)
            # Row 1: 自營商(避險)
            # Row 2: 投信
            # Row 3: 外資及陸資(不含外資自營商)
            # Row 4: 外資自營商
            # Row 5: 合計
            rows = data["data"]

            def _parse_net(row):
                try:
                    return int(str(row[3]).replace(",", "").strip())
                except (ValueError, IndexError):
                    return 0

            result = {"foreign": 0, "trust": 0, "dealer": 0}

            if len(rows) >= 5:
                # 固定行號解析（最可靠）
                result["dealer"] = _parse_net(rows[0]) + _parse_net(rows[1])  # 自營(自行) + 自營(避險)
                result["trust"] = _parse_net(rows[2])                         # 投信
                result["foreign"] = _parse_net(rows[3]) + _parse_net(rows[4]) # 外資(不含自營) + 外資自營
            else:
                # 備用：名稱比對（舊邏輯修正版）
                for row in rows:
                    name = row[0].strip()
                    net = _parse_net(row)
                    if name.startswith("外資") or "陸資" in name:
                        result["foreign"] += net
                    elif "投信" in name:
                        result["trust"] = net
                    elif name.startswith("自營"):
                        result["dealer"] += net

            # 轉換為億元
            save_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            foreign_yi = round(result["foreign"] / 100_000_000, 2)
            trust_yi = round(result["trust"] / 100_000_000, 2)
            dealer_yi = round(result["dealer"] / 100_000_000, 2)

            save_market_institutional(save_date, foreign_yi, trust_yi, dealer_yi)
            print(f"[Institutional] 大盤法人已儲存: 外資{foreign_yi:+.2f}億 投信{trust_yi:+.2f}億 自營{dealer_yi:+.2f}億")

            return {
                "date": save_date,
                "foreign_net": foreign_yi,
                "trust_net": trust_yi,
                "dealer_net": dealer_yi,
                "total_net": round(foreign_yi + trust_yi + dealer_yi, 2)
            }

        except Exception as e:
            print(f"[Institutional] 抓取大盤法人失敗: {e}")
            traceback.print_exc()
            return None

    # ==========================================
    # TWSE API 抓取 - 個股三大法人
    # ==========================================

    def fetch_stock_institutional(self, date_str: str = None):
        """
        抓取個股三大法人買賣超
        API: https://www.twse.com.tw/fund/T86?response=json&date=YYYYMMDD&selectType=ALLBUT0999
        """
        if not date_str:
            date_str = date.today().strftime("%Y%m%d")
        else:
            date_str = date_str.replace("-", "")

        url = f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"

        try:
            print(f"[Institutional] 抓取個股法人資料: {date_str}")
            # TWSE 有速率限制，先等一下
            time.sleep(3)

            resp = httpx.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            data = resp.json()

            if data.get("stat") != "OK" or not data.get("data"):
                print(f"[Institutional] 個股法人資料尚未公布: {date_str}")
                return []

            # 取得關注清單的股票代號
            watchlist = get_watchlist()
            watch_ids = set(w["stock_id"] for w in watchlist)

            if not watch_ids:
                print("[Institutional] 關注清單為空，跳過個股法人抓取")
                return []

            save_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            results = []

            # data["data"] 每列格式：
            # [0]證券代號, [1]證券名稱, [2]外資買超股數, [3]外資賣超股數, [4]外資買賣超,
            # [5]外資自營買超, [6]外資自營賣超, [7]外資自營買賣超,
            # [8]投信買超, [9]投信賣超, [10]投信買賣超,
            # [11]自營商買超(自行), [12]自營商賣超(自行), [13]自營商買賣超(自行),
            # [14]自營商買超(避險), [15]自營商賣超(避險), [16]自營商買賣超(避險),
            # [17]三大法人合計
            for row in data["data"]:
                stock_id = row[0].strip()

                if stock_id not in watch_ids:
                    continue

                try:
                    stock_name = row[1].strip()

                    def parse_int(val):
                        return int(str(val).replace(",", "").strip())

                    foreign_buy = parse_int(row[2])
                    foreign_sell = parse_int(row[3])
                    trust_buy = parse_int(row[8])
                    trust_sell = parse_int(row[9])
                    # 自營商 = 自行 + 避險
                    dealer_buy = parse_int(row[11]) + parse_int(row[14])
                    dealer_sell = parse_int(row[12]) + parse_int(row[15])

                    save_stock_institutional(
                        save_date, stock_id, stock_name,
                        foreign_buy, foreign_sell,
                        trust_buy, trust_sell,
                        dealer_buy, dealer_sell
                    )

                    results.append({
                        "stock_id": stock_id,
                        "stock_name": stock_name,
                        "foreign_net": foreign_buy - foreign_sell,
                        "trust_net": trust_buy - trust_sell,
                        "dealer_net": dealer_buy - dealer_sell,
                        "total_net": parse_int(row[17]) if len(row) > 17 else 0
                    })

                except (ValueError, IndexError) as e:
                    print(f"[Institutional] 解析 {stock_id} 失敗: {e}")
                    continue

            print(f"[Institutional] 已儲存 {len(results)} 檔個股法人資料")
            return results

        except Exception as e:
            print(f"[Institutional] 抓取個股法人失敗: {e}")
            traceback.print_exc()
            return []

    # ==========================================
    # 統一排程任務
    # ==========================================

    def scheduled_fetch(self):
        """排程任務：抓取所有法人資料"""
        today = date.today()

        # 週末不抓
        if today.weekday() >= 5:
            print(f"[Institutional] 今天是週末，跳過抓取")
            return

        # 避免重複抓取
        if self.last_fetch_date == today.isoformat():
            print(f"[Institutional] 今日已抓取過，跳過")
            return

        self.last_fetch_status = "fetching"
        print(f"[Institutional] ===== 開始自動排程抓取法人資料 =====")

        try:
            # 1. 大盤法人
            market_result = self.fetch_market_institutional()

            # 2. 個股法人（間隔 3 秒避免被封鎖）
            stock_results = self.fetch_stock_institutional()

            self.last_fetch_date = today.isoformat()
            self.last_fetch_status = "success"
            print(f"[Institutional] ===== 法人資料抓取完成 =====")

        except Exception as e:
            self.last_fetch_status = f"error: {e}"
            print(f"[Institutional] 排程任務失敗: {e}")

    def manual_fetch(self, date_str: str = None):
        """手動觸發抓取（可指定日期）"""
        print(f"[Institutional] 手動觸發抓取: {date_str or '今日'}")
        self.last_fetch_status = "fetching"

        try:
            market = self.fetch_market_institutional(date_str)
            stocks = self.fetch_stock_institutional(date_str)
            self.last_fetch_status = "success"
            return {"market": market, "stocks": stocks}
        except Exception as e:
            self.last_fetch_status = f"error: {e}"
            return {"error": str(e)}

    # ==========================================
    # 啟動 / 停止
    # ==========================================

    def start(self):
        """啟動排程器"""
        if self.is_running:
            return

        # 每日 18:05 執行一次
        self.scheduler.add_job(
            self.scheduled_fetch,
            trigger="cron",
            hour=18,
            minute=5,
            id="fetch_institutional",
            replace_existing=True
        )

        # 如果啟動時已過 18:05 且今天還沒抓過，立即補抓
        now = datetime.now()
        if now.hour >= 18 and self.last_fetch_date != date.today().isoformat():
            threading.Thread(target=self.scheduled_fetch, daemon=True).start()

        self.scheduler.start()
        self.is_running = True
        print("[Institutional Worker] 排程啟動：每日 18:05 自動抓取法人資料")

    def stop(self):
        """停止排程器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.is_running = False
        print("[Institutional Worker] 已停止")


# 全域單例
institutional_worker = InstitutionalWorker()
