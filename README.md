# Taiwan Stock Dashboard

**台股戰情室** - 一站式台股交易管理系統

> 專為台股投資人打造的個人化看盤工具，整合即時行情、三大法人籌碼、AI 智慧選股、交易紀錄管理與績效追蹤，讓你從盤前準備到盤後檢討都在同一個介面完成。

## Why This Project?

身為散戶，每天要開一堆網頁查行情、看法人、記交易、寫日記... 很累。

這個系統把所有東西整合在一起：

- 盤中：即時行情 + 到價提醒，不用一直盯盤
- 盤後：自動抓法人籌碼、融資融券，AI 幫你產生每日檢討
- 長期：績效追蹤、日曆視圖、AI 推薦回測，看得到自己的成長

**全部 self-hosted，資料在自己電腦，不用擔心隱私。**

## Features

### 即時行情
透過永豐 Shioaji API 取得即時報價，包含 VWAP（成交量加權均價）、最高最低、成交量等，盤中每 15 秒自動更新。

### 關注清單 & 持倉管理
區分「持有」與「觀察」股票，持倉自動計算未實現損益。支援整股與零股交易紀錄，手續費折扣和交易稅自動計算。

### 三大法人籌碼
自動抓取 TWSE 公開資料，顯示大盤三大法人買賣超（外資/投信/自營），以及個股法人進出明細。

### 融資融券
個股融資餘額、融券餘額、當沖比例一目了然，判斷市場多空情緒。

### AI 智慧分析
接入 Google Gemini AI，提供：
- **每日盤後檢討**：自動分析當天操作，給出評分與建議
- **AI 選股推薦**：附帶理由、目標價、停損價
- **推薦回測**：追蹤 AI 推薦的後續表現，驗證準確度

### 到價提醒
設定突破/跌破價位，觸發時透過 Telegram 即時通知，不用一直盯盤。

### 每日交易日記
AI 自動生成檢討 + 手動筆記，記錄當天心態標籤（冷靜/衝動/恐慌/貪婪/紀律），養成覆盤習慣。

### 績效追蹤
- **損益曲線**：視覺化累計損益走勢
- **月報統計**：勝率、總交易次數、手續費統計
- **日曆視圖**：以日曆方式瀏覽每日損益，紅色賺錢、綠色虧損

### 集保大戶資料（TDCC）
分析大戶/中實戶/散戶的持股比例變化，觀察籌碼集中度。

### Telegram 通知
盤後自動推播：
- 三大法人買賣超速報
- AI 每日檢討報告
- 到價提醒觸發通知

## Tech Stack

| 層級 | 技術 |
|------|------|
| Backend | Python 3.10+ / FastAPI / Uvicorn |
| Frontend | Vanilla HTML + CSS + JavaScript（無框架，輕量） |
| Database | SQLite（WAL mode，12 張資料表）|
| Market Data | 永豐 Shioaji API（即時行情）/ TWSE Open Data（法人、融資融券）|
| AI | Google Gemini (gemini-2.5-flash) |
| Notification | Telegram Bot API |
| Scheduler | APScheduler（盤後自動排程）|

## Architecture

```
Browser (localhost:8000)
    │
    ├── Static Frontend (HTML/CSS/JS)
    │
    └── FastAPI Backend
            ├── 11 REST API Routers
            ├── Background Workers
            │     ├── Shioaji Worker (每15秒輪詢行情)
            │     ├── Institutional Worker (盤後抓法人)
            │     ├── Margin Worker (盤後抓融資融券)
            │     ├── AI Analyzer (Gemini 分析引擎)
            │     ├── Alert Manager (到價監控)
            │     ├── TDCC Worker (集保資料)
            │     └── Telegram Bot (推播通知)
            │
            └── SQLite Database (WAL mode)
```

## Quick Start

### 1. Clone

```bash
git clone https://github.com/SeanFuture9999/stock-game1.git
cd stock-game1
```

### 2. Install

```bash
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
```

編輯 `.env` 填入你的 API Key：

| 項目 | 用途 | 申請連結 |
|------|------|----------|
| Shioaji API | 即時行情 | [永豐證券 OpenAPI](https://www.sinotrade.com.tw/openapi) |
| Google Gemini | AI 分析 | [Google AI Studio](https://aistudio.google.com/apikey) |
| Telegram Bot | 推播通知（選填）| [BotFather](https://t.me/BotFather) |

### 4. Run

```bash
python main.py
```

開啟瀏覽器 http://localhost:8000

### 5. Demo Data (Optional)

不想接 API，只想看展示效果？產生模擬資料：

```bash
python scripts/seed_demo.py
```

## Screenshots

> 截圖請放在 `screenshots/` 資料夾

<!--
![即時行情](screenshots/dashboard.png)
![法人籌碼](screenshots/institutional.png)
![AI 推薦](screenshots/ai.png)
![績效總覽](screenshots/performance.png)
![日曆視圖](screenshots/calendar.png)
-->

## Project Structure

```
stock-game/
├── main.py                 # FastAPI 主程式入口
├── config.py               # 環境變數設定
├── requirements.txt        # Python 套件
├── .env.example            # 環境變數範本
│
├── database/
│   ├── db.py               # SQLite 連線與建表（12 張資料表）
│   └── models.py           # CRUD 操作
│
├── routes/                 # 11 個 API 路由模組
│   ├── routes_stock.py     # 即時行情
│   ├── routes_watchlist.py # 關注清單 & 持倉
│   ├── routes_trade.py     # 交易紀錄
│   ├── routes_institutional.py  # 法人籌碼
│   ├── routes_margin.py    # 融資融券
│   ├── routes_ai.py        # AI 推薦 + 回測
│   ├── routes_alert.py     # 到價提醒
│   ├── routes_diary.py     # 每日日記
│   ├── routes_performance.py    # 績效統計
│   ├── routes_settings.py  # 系統設定
│   └── routes_tdcc.py      # 集保資料
│
├── workers/                # 7 個背景工作模組
│   ├── shioaji_worker.py   # Shioaji 即時行情輪詢
│   ├── institutional_worker.py  # TWSE 法人資料排程
│   ├── ai_analyzer.py      # Gemini AI 分析引擎
│   ├── alert_manager.py    # 到價提醒監控
│   ├── margin_worker.py    # TWSE 融資融券排程
│   ├── telegram_bot.py     # Telegram 通知服務
│   └── tdcc_worker.py      # TDCC 集保資料排程
│
├── static/                 # 前端（純 HTML/CSS/JS）
│   ├── index.html          # 主頁面（9 個功能分頁）
│   ├── app.js              # 前端邏輯
│   └── style.css           # 深色主題樣式
│
└── scripts/
    └── seed_demo.py        # 模擬資料產生器
```

## Scheduled Tasks

系統使用 APScheduler 在盤後自動執行：

| 時間 | 任務 | 說明 |
|------|------|------|
| 18:05 | 法人籌碼 | 抓取 TWSE BFI82U + T86 資料 |
| 18:10 | 融資融券 | 抓取 TWSE MI_MARGN 資料 |
| 18:15 | AI 檢討 | Gemini 自動產生每日報告 |
| 每週五 18:30 | 集保資料 | 更新 TDCC 大戶持股比例 |

## Requirements

- Python 3.10+
- 永豐證券帳號（申請 Shioaji API）
- Google AI Studio API Key（免費額度即可）
- Telegram Bot Token（選填，用於推播通知）

## License

MIT License

## Disclaimer

本系統僅供個人學習與研究使用，不構成任何投資建議。投資有風險，請自行判斷。

---

Built with FastAPI + Shioaji + Google Gemini AI
