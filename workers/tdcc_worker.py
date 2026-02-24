"""
workers/tdcc_worker.py - 集保大戶資料
TDCC (台灣集中保管結算所) 持股分級資料
每週五更新，顯示持股分級變化（散戶/中實戶/大戶/千張大戶比例）
"""
import httpx
import traceback
from datetime import datetime, date, timedelta
from database.db import get_db_sync


class TDCCWorker:
    """集保大戶資料抓取"""

    def __init__(self):
        self.last_fetch_date = None
        self.base_url = "https://www.tdcc.com.tw/api/v1/stock"

    # ==========================================
    # 抓取集保資料
    # ==========================================

    def fetch_tdcc_data(self, stock_id: str, target_date: str = None) -> list:
        """
        抓取指定股票的集保分級資料
        資料來源: TDCC 開放資料 API
        回傳: 各持股等級的人數和股數
        """
        if not target_date:
            # 找最近的週五
            today = date.today()
            # TDCC 每週五更新，找最近的週五
            days_since_friday = (today.weekday() - 4) % 7
            last_friday = today - timedelta(days=days_since_friday)
            target_date = last_friday.strftime("%Y%m%d")

        try:
            url = f"https://www.tdcc.com.tw/api/v1/opendata/getOD"
            # 嘗試 TDCC OpenData API
            # 備案：使用公開的 CSV 資料
            with httpx.Client(timeout=15) as client:
                # 嘗試 TDCC 官方 API
                resp = client.get(
                    "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock",
                    params={
                        "scaDates": target_date,
                        "scaDate": target_date,
                        "SqlMethod": "StockNo",
                        "StockNo": stock_id,
                        "REession": ""
                    },
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json"
                    },
                    follow_redirects=True
                )

                if resp.status_code == 200:
                    # 嘗試解析
                    try:
                        data = resp.json()
                        return self._parse_tdcc_json(stock_id, target_date, data)
                    except Exception:
                        # 非 JSON，嘗試 HTML 解析或備用方案
                        return self._fetch_tdcc_backup(stock_id, target_date)
                else:
                    return self._fetch_tdcc_backup(stock_id, target_date)

        except Exception as e:
            print(f"[TDCC] 抓取 {stock_id} 失敗: {e}")
            return self._fetch_tdcc_backup(stock_id, target_date)

    def _fetch_tdcc_backup(self, stock_id: str, target_date: str) -> list:
        """
        備用方案：使用公開資料 API
        goodinfo 或 finmind 等替代來源
        """
        try:
            # 使用 FinMind 開放資料
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    "https://api.finmindtrade.com/api/v4/data",
                    params={
                        "dataset": "TaiwanStockHoldingSharesPer",
                        "data_id": stock_id,
                        "start_date": (date.today() - timedelta(days=14)).isoformat(),
                        "end_date": date.today().isoformat()
                    }
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == 200 and data.get("data"):
                        return self._parse_finmind_data(stock_id, data["data"])

        except Exception as e:
            print(f"[TDCC] 備用 API 也失敗: {e}")

        return []

    def _parse_tdcc_json(self, stock_id: str, target_date: str, data) -> list:
        """解析 TDCC 官方 JSON 資料"""
        results = []
        # TDCC 分級：1-999, 1000-5000, 5001-10000, 10001-15000, ...400001以上
        # 每級有 人數 和 股數
        if isinstance(data, list):
            for item in data:
                results.append({
                    "stock_id": stock_id,
                    "date": target_date,
                    "level": item.get("level", ""),
                    "holders": int(item.get("holders", 0)),
                    "shares": int(item.get("shares", 0)),
                    "percent": float(item.get("percent", 0))
                })
        return results

    def _parse_finmind_data(self, stock_id: str, data: list) -> list:
        """解析 FinMind 持股分級資料"""
        if not data:
            return []

        # 取最新一期
        latest_date = max(item["date"] for item in data)
        latest_data = [item for item in data if item["date"] == latest_date]

        results = []
        for item in latest_data:
            results.append({
                "stock_id": stock_id,
                "date": latest_date,
                "level": item.get("HoldingSharesLevel", ""),
                "holders": int(item.get("people", 0)),
                "shares": int(item.get("unit", 0)),  # 單位：股
                "percent": float(item.get("percent", 0))
            })

        return results

    # ==========================================
    # 儲存到 DB
    # ==========================================

    def save_tdcc_data(self, data_list: list):
        """儲存集保資料到 DB"""
        if not data_list:
            return 0

        conn = get_db_sync()
        try:
            count = 0
            for item in data_list:
                conn.execute("""
                    INSERT INTO tdcc_data (date, stock_id, level, holders, shares, percent)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date, stock_id, level) DO UPDATE SET
                        holders = excluded.holders,
                        shares = excluded.shares,
                        percent = excluded.percent,
                        fetched_at = CURRENT_TIMESTAMP
                """, (
                    item["date"], item["stock_id"], item["level"],
                    item["holders"], item["shares"], item["percent"]
                ))
                count += 1
            conn.commit()
            print(f"[TDCC] 已儲存 {count} 筆集保資料")
            return count
        except Exception as e:
            print(f"[TDCC] 儲存失敗: {e}")
            return 0
        finally:
            conn.close()

    def fetch_and_save(self, stock_ids: list) -> int:
        """批次抓取並儲存"""
        import time
        total = 0
        for stock_id in stock_ids:
            data = self.fetch_tdcc_data(stock_id)
            if data:
                total += self.save_tdcc_data(data)
            time.sleep(2)  # 避免請求過快

        self.last_fetch_date = date.today().isoformat()
        print(f"[TDCC] 批次抓取完成，共 {total} 筆")
        return total

    # ==========================================
    # 查詢
    # ==========================================

    def get_tdcc_summary(self, stock_id: str) -> dict:
        """
        取得集保摘要：大戶(400張以上)、中實戶(100-400張)、散戶(100張以下) 的持股比例
        """
        conn = get_db_sync()
        try:
            # 取最新資料
            rows = conn.execute("""
                SELECT * FROM tdcc_data
                WHERE stock_id = ? AND date = (
                    SELECT MAX(date) FROM tdcc_data WHERE stock_id = ?
                )
                ORDER BY level
            """, (stock_id, stock_id)).fetchall()

            if not rows:
                return {"stock_id": stock_id, "data": [], "summary": None}

            data = [dict(r) for r in rows]
            data_date = data[0]["date"] if data else ""

            # 嘗試分類（依等級名稱分析）
            retail_shares = 0  # 散戶 (< 100張)
            medium_shares = 0  # 中實戶 (100-400張)
            big_shares = 0     # 大戶 (> 400張)
            total_shares = sum(d["shares"] for d in data)

            for d in data:
                level = d["level"]
                shares = d["shares"]
                # 判斷等級（依持股數分類）
                # FinMind 格式：「1-999」「1,000-5,000」...
                try:
                    # 嘗試解析等級範圍
                    level_clean = level.replace(",", "").replace(" ", "")
                    if "-" in level_clean:
                        parts = level_clean.split("-")
                        upper = int(parts[-1]) if parts[-1].isdigit() else 999999
                    elif "以上" in level_clean:
                        upper = 999999
                    else:
                        upper = int(level_clean) if level_clean.isdigit() else 0

                    # 以「張」為單位 (1張=1000股)
                    upper_zhang = upper / 1000
                    if upper_zhang < 100:
                        retail_shares += shares
                    elif upper_zhang < 400:
                        medium_shares += shares
                    else:
                        big_shares += shares
                except Exception:
                    retail_shares += shares

            return {
                "stock_id": stock_id,
                "date": data_date,
                "data": data,
                "summary": {
                    "retail_percent": round(retail_shares / total_shares * 100, 1) if total_shares > 0 else 0,
                    "medium_percent": round(medium_shares / total_shares * 100, 1) if total_shares > 0 else 0,
                    "big_percent": round(big_shares / total_shares * 100, 1) if total_shares > 0 else 0,
                    "total_shares": total_shares
                }
            }
        finally:
            conn.close()


# 全域單例
tdcc_worker = TDCCWorker()
