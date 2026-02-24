# Taiwan Stock Dashboard

**台股戰情室** - 個人台股交易管理系統

整合即時行情、法人籌碼、AI 分析、交易紀錄與績效追蹤的一站式看盤工具。

## Features

| 功能 | 說明 |
|------|------|
| 即時行情 | 透過永豐 Shioaji API 取得即時報價、VWAP、最高最低 |
| 關注清單 | 管理持有與觀察中的股票，即時損益計算 |
| 交易紀錄 | 完整買賣記錄，自動計算手續費與交易稅 |
| 法人籌碼 | 三大法人（外資/投信/自營）買賣超，大盤+個股 |
| 融資融券 | 個股融資融券餘額、當沖比例 |
| AI 推薦 | Google Gemini AI 分析推薦股票，含目標價與停損 |
| AI 回測 | 追蹤 AI 推薦的實際表現 |
| 到價提醒 | 設定突破/跌破價位，觸發 Telegram 通知 |
| 每日日記 | AI 自動產生每日檢討 + 手動筆記 |
| 績效總覽 | 累計損益曲線、月報、勝率統計 |
| 日曆視圖 | 以日曆方式瀏覽每日交易損益 |
| 集保資料 | TDCC 大戶持股比例分析 |
| Telegram | 盤後自動推播法人/AI/提醒通知 |

## Tech Stack

- **Backend:** Python 3.10+ / FastAPI / Uvicorn
- **Frontend:** Vanilla HTML + CSS + JavaScript (No Framework)
- **Data:** SQLite (WAL mode) / Shioaji API / TWSE Open Data
- **AI:** Google Gemini (gemini-2.5-flash)
- **Notification:** Telegram Bot API

## Quick Start

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/stock-game.git
cd stock-game
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
- **Shioaji API:** [永豐證券 OpenAPI](https://www.sinotrade.com.tw/openapi)
- **Google Gemini:** [Google AI Studio](https://aistudio.google.com/apikey)
- **Telegram Bot:** [BotFather](https://t.me/BotFather) (選填)

### 4. Run

```bash
python main.py
```

開啟瀏覽器 http://localhost:8000

### 5. Demo Data (Optional)

如果只想看展示效果，可以產生模擬資料：

```bash
python scripts/seed_demo.py
```

## Screenshots

> 截圖請放在 `screenshots/` 資料夾

## Project Structure

```
stock-game/
├── main.py                 # FastAPI 主程式入口
├── config.py               # 環境變數設定
├── requirements.txt        # Python 套件
├── .env.example            # 環境變數範本
│
├── database/
│   ├── db.py               # SQLite 連線與建表
│   └── models.py           # CRUD 操作
│
├── routes/
│   ├── routes_stock.py     # 即時行情 API
│   ├── routes_watchlist.py # 關注清單 API
│   ├── routes_trade.py     # 交易紀錄 API
│   ├── routes_institutional.py  # 法人籌碼 API
│   ├── routes_margin.py    # 融資融券 API
│   ├── routes_ai.py        # AI 推薦 + 回測 API
│   ├── routes_alert.py     # 到價提醒 API
│   ├── routes_diary.py     # 每日日記 API
│   ├── routes_performance.py    # 績效統計 API
│   ├── routes_settings.py  # 系統設定 API
│   └── routes_tdcc.py      # 集保資料 API
│
├── workers/
│   ├── shioaji_worker.py   # Shioaji 即時行情 Worker
│   ├── institutional_worker.py  # 法人籌碼排程
│   ├── ai_analyzer.py      # Gemini AI 分析引擎
│   ├── alert_manager.py    # 到價提醒管理
│   ├── margin_worker.py    # 融資融券排程
│   ├── telegram_bot.py     # Telegram 通知
│   └── tdcc_worker.py      # 集保資料排程
│
├── static/
│   ├── index.html          # 前端主頁面
│   ├── app.js              # 前端邏輯
│   └── style.css           # 樣式
│
└── scripts/
    └── seed_demo.py        # 模擬資料產生器
```

## Scheduled Tasks

系統會自動在盤後執行：

| 時間 | 任務 |
|------|------|
| 18:05 | 抓取三大法人買賣超 |
| 18:10 | 抓取融資融券資料 |
| 18:15 | AI 每日檢討報告 |
| 每週五 18:30 | 更新集保大戶資料 |

## License

MIT License

## Disclaimer

本系統僅供個人學習與研究使用，不構成任何投資建議。投資有風險，請自行判斷。
