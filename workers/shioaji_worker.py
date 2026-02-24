"""
workers/shioaji_worker.py - Shioaji 即時行情背景 Worker
使用 subscribe 即時推播，斷線自動重連
所有行情資料寫入記憶體快取 + SQLite
"""
import shioaji as sj
import threading
import time
import traceback
from datetime import datetime, time as dt_time
from collections import defaultdict

from config import SHIOAJI_API_KEY, SHIOAJI_SECRET_KEY, TRADING_SESSIONS
from database.models import save_snapshot, get_watchlist


class ShioajiWorker:
    """Shioaji 行情引擎（背景執行緒）"""

    def __init__(self):
        self.api = None
        self.is_connected = False
        self.is_running = False
        self._thread = None
        self._lock = threading.Lock()

        # 記憶體快取：最新行情（前端直接讀這裡，毫秒級回應）
        self.cache = {}          # {stock_id: {price, change_percent, ...}}
        self.last_update = None  # 最後更新時間
        self.subscribed_stocks = set()

        # 斷線重連
        self._retry_count = 0
        self._max_retry = 10
        self._retry_delays = [5, 10, 15, 30, 60, 60, 120, 120, 300, 300]

    # ==========================================
    # 連線管理
    # ==========================================

    def connect(self):
        """連線到 Shioaji API"""
        with self._lock:
            if self.is_connected:
                return True

            try:
                print("[Shioaji] 正在連線...")
                self.api = sj.Shioaji()
                self.api.login(
                    api_key=SHIOAJI_API_KEY,
                    secret_key=SHIOAJI_SECRET_KEY,
                    fetch_contract=True
                )

                # 等待合約載入
                for i in range(20):
                    try:
                        if "2330" in self.api.Contracts.Stocks:
                            break
                    except Exception:
                        pass
                    time.sleep(1)

                self.is_connected = True
                self._retry_count = 0
                print("[Shioaji] 連線成功！合約已載入")
                return True

            except Exception as e:
                print(f"[Shioaji] 連線失敗: {e}")
                self.is_connected = False
                return False

    def disconnect(self):
        """安全斷線"""
        with self._lock:
            try:
                if self.api and self.is_connected:
                    self.api.logout()
                    print("[Shioaji] 已安全登出")
            except Exception as e:
                print(f"[Shioaji] 登出異常: {e}")
            finally:
                self.is_connected = False
                self.subscribed_stocks.clear()

    def reconnect(self):
        """斷線重連（漸進式延遲）"""
        self.disconnect()
        delay_idx = min(self._retry_count, len(self._retry_delays) - 1)
        delay = self._retry_delays[delay_idx]
        self._retry_count += 1

        if self._retry_count > self._max_retry:
            print(f"[Shioaji] 已達最大重試次數 ({self._max_retry})，停止重連")
            return False

        print(f"[Shioaji] 第 {self._retry_count} 次重連，等待 {delay} 秒...")
        time.sleep(delay)
        return self.connect()

    # ==========================================
    # 行情抓取（polling 模式，穩定可靠）
    # ==========================================

    def fetch_snapshots(self, stock_ids: list):
        """
        批次抓取快照（polling 方式）
        Shioaji subscribe 在部分環境不穩，改用定時 polling + 快取
        """
        if not self.is_connected or not self.api:
            return {}

        try:
            contracts = []
            valid_ids = []
            for sid in stock_ids:
                try:
                    contract = self.api.Contracts.Stocks[sid]
                    if contract:
                        contracts.append(contract)
                        valid_ids.append(sid)
                except Exception:
                    continue

            if not contracts:
                return {}

            snapshots = self.api.snapshots(contracts)
            now_str = datetime.now().strftime("%H:%M:%S")
            results = {}

            for i, snap in enumerate(snapshots):
                sid = valid_ids[i]
                contract = contracts[i]

                price = snap.close
                volume = snap.total_volume
                total_amount = getattr(snap, 'total_amount', 0) or 0

                # VWAP：優先使用 Shioaji 提供的 average_price
                avg_price = getattr(snap, 'average_price', 0) or 0
                if avg_price > 0:
                    vwap = avg_price
                elif volume > 0 and total_amount > 0:
                    # 備用：用 total_amount / total_volume 計算
                    vwap = total_amount / volume
                else:
                    vwap = price

                data = {
                    "stock_id": sid,
                    "stock_name": contract.name,
                    "price": price,
                    "change_price": snap.change_price if hasattr(snap, 'change_price') else 0,
                    "change_percent": snap.change_rate if snap.change_rate is not None else 0,
                    "volume": snap.volume if hasattr(snap, 'volume') else 0,
                    "total_volume": volume,
                    "amount": total_amount,
                    "high": snap.high,
                    "low": snap.low,
                    "open": snap.open,
                    "close": price,
                    "buy_price": snap.buy_price if hasattr(snap, 'buy_price') else 0,
                    "sell_price": snap.sell_price if hasattr(snap, 'sell_price') else 0,
                    "vwap": round(vwap, 2),
                    "update_time": now_str,
                }

                results[sid] = data

                # 寫入記憶體快取
                with self._lock:
                    self.cache[sid] = data
                    self.last_update = datetime.now()

            return results

        except Exception as e:
            print(f"[Shioaji] 抓取快照失敗: {e}")
            traceback.print_exc()
            return {}

    def save_snapshots_to_db(self, results: dict):
        """將快照存入資料庫（每分鐘一次）"""
        for sid, data in results.items():
            try:
                save_snapshot(sid, data["stock_name"], data)
            except Exception as e:
                print(f"[Shioaji] 存入快照失敗 {sid}: {e}")

    # ==========================================
    # 交易時間判斷
    # ==========================================

    @staticmethod
    def is_trading_time():
        """判斷是否在交易時間（含盤前試搓 + 盤後零股）"""
        now = datetime.now().time()
        for session_name, (start_str, end_str) in TRADING_SESSIONS.items():
            h1, m1 = map(int, start_str.split(":"))
            h2, m2 = map(int, end_str.split(":"))
            if dt_time(h1, m1) <= now <= dt_time(h2, m2):
                return True
        return False

    @staticmethod
    def get_session_name():
        """取得目前交易時段"""
        now = datetime.now().time()
        for session_name, (start_str, end_str) in TRADING_SESSIONS.items():
            h1, m1 = map(int, start_str.split(":"))
            h2, m2 = map(int, end_str.split(":"))
            if dt_time(h1, m1) <= now <= dt_time(h2, m2):
                return session_name
        return "closed"

    # ==========================================
    # 背景執行緒主迴圈
    # ==========================================

    def _worker_loop(self):
        """背景執行緒主迴圈"""
        print("[Shioaji Worker] 背景執行緒啟動")
        save_counter = 0  # 每 N 次 polling 存一次 DB

        while self.is_running:
            try:
                if not self.is_trading_time():
                    # 非交易時間，每 60 秒檢查一次
                    time.sleep(60)
                    continue

                if not self.is_connected:
                    if not self.reconnect():
                        time.sleep(60)
                        continue

                # 從資料庫取得關注清單
                watchlist = get_watchlist()
                stock_ids = [w["stock_id"] for w in watchlist]

                if not stock_ids:
                    time.sleep(30)
                    continue

                # 抓取快照
                results = self.fetch_snapshots(stock_ids)

                if results:
                    save_counter += 1
                    # 每分鐘存一次到 DB（polling 間隔 15 秒 × 4 = 60 秒）
                    if save_counter >= 4:
                        self.save_snapshots_to_db(results)
                        save_counter = 0

                # 盤中每 15 秒更新一次
                time.sleep(15)

            except Exception as e:
                print(f"[Shioaji Worker] 迴圈異常: {e}")
                traceback.print_exc()
                # 嘗試重連
                if not self.reconnect():
                    time.sleep(120)

        print("[Shioaji Worker] 背景執行緒結束")

    # ==========================================
    # 啟動 / 停止
    # ==========================================

    def start(self):
        """啟動背景 Worker"""
        if self.is_running:
            return

        if not self.connect():
            print("[Shioaji Worker] 初始連線失敗，Worker 仍會啟動並持續重試")

        self.is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="shioaji-worker")
        self._thread.start()
        print("[Shioaji Worker] 已啟動")

    def stop(self):
        """停止背景 Worker"""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=10)
        self.disconnect()
        print("[Shioaji Worker] 已停止")

    def get_cache(self):
        """取得快取中的所有行情（前端用）"""
        with self._lock:
            return dict(self.cache)

    def get_stock_cache(self, stock_id: str):
        """取得單一股票的快取行情"""
        with self._lock:
            return self.cache.get(stock_id)

    def get_stock_name(self, stock_id: str) -> str:
        """透過 API 取得股票名稱"""
        if not self.is_connected or not self.api:
            return ""
        try:
            contract = self.api.Contracts.Stocks[stock_id]
            return contract.name if contract else ""
        except Exception:
            return ""

    def is_valid_stock(self, stock_id: str) -> bool:
        """檢查股票代號是否有效"""
        if not self.is_connected or not self.api:
            return False
        try:
            contract = self.api.Contracts.Stocks[stock_id]
            return contract is not None
        except Exception:
            return False


# 全域單例
worker = ShioajiWorker()
