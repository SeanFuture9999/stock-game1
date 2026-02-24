/**
 * app.js - 台股戰情室前端邏輯
 * 每 60 秒自動刷新行情，所有 API 呼叫都走 FastAPI 後端
 */

// ==========================================
// 全域狀態
// ==========================================
let currentTab = 'dashboard';
let selectedEmotion = '';
let refreshTimer = null;
const REFRESH_INTERVAL = 60 * 1000; // 60 秒

// ==========================================
// 初始化
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    // 設定今日日期
    const today = new Date().toISOString().split('T')[0];
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(input => input.value = today);

    // 啟動
    updateClock();
    setInterval(updateClock, 1000);
    loadAll();
    startAutoRefresh();

    // 每 30 秒檢查到價提醒觸發
    setInterval(pollAlertTriggers, 30000);

    // Enter 鍵新增股票
    document.getElementById('add-stock-input').addEventListener('keypress', e => {
        if (e.key === 'Enter') addStock();
    });

    // 交易價格/股數變動時預覽費用
    ['trade-shares', 'trade-price', 'trade-action', 'trade-stock-id'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', previewFees);
    });
});

// ==========================================
// Tab 切換
// ==========================================
function showTab(tab) {
    currentTab = tab;

    // 更新 tab 按鈕
    document.querySelectorAll('.sidebar-nav button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // 更新內容
    document.querySelectorAll('.tab-content').forEach(el => {
        el.classList.remove('active');
    });
    document.getElementById(`tab-${tab}`).classList.add('active');

    // 更新標題
    const titles = {
        dashboard: '💹 即時行情',
        trade: '📝 交易紀錄',
        performance: '📈 績效總覽',
        calendar: '📅 日曆視圖',
        institutional: '📊 法人籌碼',
        ai: '🤖 AI 推薦',
        alerts: '🔔 到價提醒',
        diary: '📓 每日日記',
        settings: '⚙️ 設定'
    };
    document.getElementById('page-title').textContent = titles[tab] || '';

    // 切換到對應 tab 時載入資料
    if (tab === 'trade') loadTrades();
    if (tab === 'performance') { loadPerfSummary(); loadDailyPnl(); loadMonthlyReport(); loadPortfolioDist(); }
    if (tab === 'calendar') loadCalendar();
    if (tab === 'institutional') loadInstitutional();
    if (tab === 'ai') { loadMarginData(); loadBacktest(); }
    if (tab === 'alerts') loadAlerts();
    if (tab === 'diary') {
        // 從側邊欄直接進日記時，隱藏返回日曆按鈕
        const backBtn = document.getElementById('btn-back-calendar');
        if (backBtn) backBtn.style.display = 'none';
        loadDiary();
    }
    if (tab === 'settings') loadSettings();
}

// ==========================================
// 時鐘 & 狀態
// ==========================================
function updateClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-TW', { hour12: false });
    document.getElementById('badge-time').textContent = timeStr;

    const h = now.getHours();
    const m = now.getMinutes();
    const mins = h * 60 + m;
    const badgeSession = document.getElementById('badge-session');

    if (mins >= 510 && mins < 540) {
        badgeSession.textContent = '盤前試搓';
        badgeSession.className = 'badge badge-yellow';
    } else if (mins >= 540 && mins < 810) {
        badgeSession.textContent = '交易中 🟢';
        badgeSession.className = 'badge badge-green';
    } else if (mins >= 820 && mins < 870) {
        badgeSession.textContent = '盤後零股';
        badgeSession.className = 'badge badge-yellow';
    } else {
        badgeSession.textContent = '已收盤';
        badgeSession.className = 'badge badge-red';
    }
}

// ==========================================
// 自動刷新
// ==========================================
function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
        if (currentTab === 'dashboard') {
            loadQuotes();
            loadPortfolio();
        }
    }, REFRESH_INTERVAL);
}

function loadAll() {
    loadWatchlist();
    loadQuotes();
    loadPortfolio();
    loadWorkerStatus();
    loadInstitutional();
}

// ==========================================
// API 工具函數
// ==========================================
async function api(path, options = {}) {
    try {
        const resp = await fetch(path, {
            headers: { 'Content-Type': 'application/json' },
            ...options
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || '請求失敗');
        }
        return await resp.json();
    } catch (e) {
        console.error(`API Error [${path}]:`, e);
        throw e;
    }
}

// ==========================================
// Toast 通知
// ==========================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ==========================================
// Worker 狀態
// ==========================================
async function loadWorkerStatus() {
    try {
        const data = await api('/api/stock/status');
        const badge = document.getElementById('badge-connection');
        if (data.is_connected) {
            badge.textContent = '✅ 已連線';
            badge.className = 'badge badge-green';
        } else {
            badge.textContent = '❌ 未連線';
            badge.className = 'badge badge-red';
        }
    } catch (e) {
        document.getElementById('badge-connection').textContent = '⚠️ 錯誤';
    }
}

// ==========================================
// 關注清單
// ==========================================
async function loadWatchlist() {
    try {
        const data = await api('/api/watchlist/');
        const holdList = document.getElementById('sidebar-hold-list');
        const watchList = document.getElementById('sidebar-watch-list');

        holdList.innerHTML = '';
        watchList.innerHTML = '';

        data.data.forEach(item => {
            const div = document.createElement('div');
            div.className = 'stock-list-item';

            const changeClass = item.change_percent > 0 ? 'up' : (item.change_percent < 0 ? 'down' : 'flat');
            const changeSign = item.change_percent > 0 ? '+' : '';

            div.innerHTML = `
                <div>
                    <span style="font-weight:600;">${item.stock_id}</span>
                    <span style="font-size:12px; color: var(--text-muted);"> ${item.stock_name}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="stock-price">${item.price ? item.price.toFixed(1) : '--'}</span>
                    <span class="stock-change ${changeClass}">${item.price ? changeSign + item.change_percent.toFixed(1) + '%' : ''}</span>
                    <button class="stock-remove-btn" onclick="removeStock('${item.stock_id}', event)" title="移除">✕</button>
                </div>
            `;

            if (item.category === 'hold') {
                holdList.appendChild(div);
            } else {
                watchList.appendChild(div);
            }
        });

        if (!holdList.children.length) holdList.innerHTML = '<div style="font-size:12px; color: var(--text-muted); padding: 4px 12px;">尚無持有股票</div>';
        if (!watchList.children.length) watchList.innerHTML = '<div style="font-size:12px; color: var(--text-muted); padding: 4px 12px;">尚無關注股票</div>';

    } catch (e) {
        console.error('載入 watchlist 失敗:', e);
    }
}

async function addStock() {
    const input = document.getElementById('add-stock-input');
    const category = document.getElementById('add-stock-category').value;
    const stockId = input.value.trim();

    if (!stockId) return;

    try {
        const data = await api('/api/watchlist/add', {
            method: 'POST',
            body: JSON.stringify({ stock_id: stockId, category: category })
        });
        showToast(data.message, 'success');
        input.value = '';
        loadWatchlist();
        loadQuotes();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function removeStock(stockId, event) {
    event.stopPropagation();
    if (!confirm(`確定移除 ${stockId}？`)) return;

    try {
        await api(`/api/watchlist/remove/${stockId}`, { method: 'DELETE' });
        showToast(`已移除 ${stockId}`, 'info');
        loadWatchlist();
        loadQuotes();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// ==========================================
// 即時行情
// ==========================================
async function loadQuotes() {
    try {
        const holdData = await api('/api/watchlist/?category=hold');
        const watchData = await api('/api/watchlist/?category=watch');

        renderQuoteTable('hold-table-body', holdData.data, false);
        renderQuoteTable('watch-table-body', watchData.data, true);

        // 同時更新側邊欄
        loadWatchlist();
    } catch (e) {
        console.error('載入行情失敗:', e);
    }
}

function renderQuoteTable(tbodyId, items, showRemove) {
    const tbody = document.getElementById(tbodyId);
    if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="${showRemove ? 9 : 8}" style="text-align:center; color: var(--text-muted);">尚無資料</td></tr>`;
        return;
    }

    tbody.innerHTML = items.map(item => {
        const changeClass = item.change_percent > 0 ? 'up' : (item.change_percent < 0 ? 'down' : 'flat');
        const changeSign = item.change_percent > 0 ? '+' : '';
        const vol = item.volume ? (item.volume > 10000 ? (item.volume / 1000).toFixed(0) + 'K' : item.volume.toLocaleString()) : '--';

        return `<tr>
            <td>${item.stock_id}</td>
            <td>${item.stock_name || '--'}</td>
            <td class="price">${item.price ? item.price.toFixed(2) : '--'}</td>
            <td class="${changeClass}" style="font-weight:600;">${item.price ? changeSign + item.change_percent.toFixed(2) + '%' : '--'}</td>
            <td class="volume">${vol}</td>
            <td class="price">${item.vwap ? item.vwap.toFixed(2) : '--'}</td>
            <td>${item.high ? item.high.toFixed(2) : '--'}</td>
            <td>${item.low ? item.low.toFixed(2) : '--'}</td>
            ${showRemove ? `<td><button class="btn btn-danger btn-sm" onclick="removeStock('${item.stock_id}', event)">✕</button></td>` : ''}
        </tr>`;
    }).join('');
}

async function refreshQuotes() {
    try {
        showToast('正在刷新...', 'info');
        await api('/api/stock/refresh', { method: 'POST' });
        await loadQuotes();
        await loadPortfolio();
        await loadWorkerStatus();
        showToast('行情已更新', 'success');
    } catch (e) {
        showToast('刷新失敗: ' + e.message, 'error');
    }
}

// ==========================================
// 持倉損益
// ==========================================
async function loadPortfolio() {
    try {
        const data = await api('/api/watchlist/portfolio');
        const summary = data.summary;

        // 更新摘要
        setValueWithColor('total-market-value', summary.total_market_value, true);
        setValueWithColor('total-unrealized', summary.total_unrealized_profit);
        setValueWithColor('total-realized', summary.total_realized_profit);

        // 更新時間
        document.getElementById('portfolio-update-time').textContent =
            data.data.length ? `最後更新: ${data.data[0]?.update_time || '--'}` : '';

        // 持倉卡片
        const container = document.getElementById('portfolio-cards');
        if (!data.data.length || data.data.every(p => p.total_shares === 0)) {
            container.innerHTML = '<div style="color: var(--text-muted); font-size: 14px;">尚無持倉</div>';
            return;
        }

        container.innerHTML = data.data
            .filter(p => p.total_shares > 0)
            .map(p => {
                const profitClass = p.unrealized_profit >= 0 ? 'up' : 'down';
                const sign = p.unrealized_profit >= 0 ? '+' : '';
                return `
                <div class="portfolio-card">
                    <div class="stock-header">
                        <div>
                            <div class="stock-name">${p.stock_name || p.stock_id}</div>
                            <div class="stock-id">${p.stock_id}</div>
                        </div>
                        <span class="price" style="font-size: 20px;">${p.current_price ? p.current_price.toFixed(2) : '--'}</span>
                    </div>
                    <div class="profit-row">
                        <span class="profit-label">持有股數</span>
                        <span>${p.total_shares.toLocaleString()}</span>
                    </div>
                    <div class="profit-row">
                        <span class="profit-label">均價成本</span>
                        <span>${p.avg_cost.toFixed(2)}</span>
                    </div>
                    <div class="profit-row">
                        <span class="profit-label">未實現損益</span>
                        <span class="${profitClass}" style="font-weight:700;">
                            ${sign}${p.unrealized_profit.toLocaleString()} (${sign}${p.unrealized_percent.toFixed(1)}%)
                        </span>
                    </div>
                    <div class="profit-row">
                        <span class="profit-label">市值</span>
                        <span>${p.market_value.toLocaleString()}</span>
                    </div>
                </div>`;
            }).join('');

    } catch (e) {
        console.error('載入持倉失敗:', e);
    }
}

function setValueWithColor(elementId, value, noColor = false) {
    const el = document.getElementById(elementId);
    const formatted = typeof value === 'number'
        ? (value >= 0 ? '+' : '') + value.toLocaleString(undefined, { maximumFractionDigits: 0 })
        : '--';
    el.textContent = formatted;

    if (!noColor) {
        if (value > 0) el.style.color = 'var(--accent-red)';
        else if (value < 0) el.style.color = 'var(--accent-green)';
        else el.style.color = 'var(--text-primary)';
    } else {
        el.style.color = 'var(--text-primary)';
        el.textContent = typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '--';
    }
}

// ==========================================
// 交易紀錄
// ==========================================
async function previewFees() {
    const stockId = document.getElementById('trade-stock-id').value.trim();
    const action = document.getElementById('trade-action').value;
    const shares = parseInt(document.getElementById('trade-shares').value) || 0;
    const price = parseFloat(document.getElementById('trade-price').value) || 0;

    if (!shares || !price) {
        document.getElementById('fee-preview').style.display = 'none';
        return;
    }

    try {
        const data = await api('/api/trade/calc-fees', {
            method: 'POST',
            body: JSON.stringify({ stock_id: stockId, action, shares, price })
        });

        const fees = data.data;
        const actionText = action === 'buy' ? '買入' : '賣出';
        const preview = document.getElementById('fee-preview');
        preview.style.display = 'block';
        preview.innerHTML = `
            <div style="display:flex; gap:24px; flex-wrap:wrap;">
                <span>💰 成交金額: <b>${fees.total_amount.toLocaleString()}</b></span>
                <span>🏦 手續費: <b>${fees.fee.toLocaleString()}</b></span>
                ${action === 'sell' ? `<span>🏛️ 交易稅: <b>${fees.tax.toLocaleString()}</b></span>` : ''}
                <span>📊 ${actionText}淨額: <b style="color: ${action === 'buy' ? 'var(--accent-red)' : 'var(--accent-green)'};">${fees.net_amount.toLocaleString()}</b></span>
            </div>
        `;
    } catch (e) {
        console.error('試算費用失敗:', e);
    }
}

async function submitTrade() {
    const stockId = document.getElementById('trade-stock-id').value.trim();
    const action = document.getElementById('trade-action').value;
    const shares = parseInt(document.getElementById('trade-shares').value);
    const price = parseFloat(document.getElementById('trade-price').value);
    const isOddLot = document.getElementById('trade-odd-lot').checked;
    const note = document.getElementById('trade-note').value.trim();

    if (!stockId || !shares || !price) {
        showToast('請填寫完整交易資訊', 'error');
        return;
    }

    try {
        const data = await api('/api/trade/add', {
            method: 'POST',
            body: JSON.stringify({
                stock_id: stockId,
                action, shares, price,
                is_odd_lot: isOddLot,
                note
            })
        });

        showToast(data.message, 'success');

        // 清空表單
        document.getElementById('trade-stock-id').value = '';
        document.getElementById('trade-shares').value = '';
        document.getElementById('trade-price').value = '';
        document.getElementById('trade-note').value = '';
        document.getElementById('trade-odd-lot').checked = false;
        document.getElementById('fee-preview').style.display = 'none';

        // 重新載入
        loadTrades();
        loadPortfolio();
        loadWatchlist();
    } catch (e) {
        showToast('交易記錄失敗: ' + e.message, 'error');
    }
}

async function loadTrades() {
    const dateStr = document.getElementById('trade-date-filter')?.value || new Date().toISOString().split('T')[0];

    try {
        const data = await api(`/api/trade/list?date_str=${dateStr}`);
        const tbody = document.getElementById('trade-table-body');
        const summaryDiv = document.getElementById('trade-summary');

        if (!data.data.length) {
            tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; color: var(--text-muted);">當日無交易紀錄</td></tr>';
            summaryDiv.innerHTML = '';
            return;
        }

        // 摘要
        const s = data.summary;
        summaryDiv.innerHTML = `
            <span style="color: var(--accent-red);">買入: ${s.total_buy.toLocaleString()}</span>
            <span style="color: var(--accent-green);">賣出: ${s.total_sell.toLocaleString()}</span>
            <span>手續費: ${s.total_fee.toLocaleString()}</span>
            <span>稅: ${s.total_tax.toLocaleString()}</span>
            <span style="font-weight:700; ${s.net_cashflow >= 0 ? 'color: var(--accent-green);' : 'color: var(--accent-red);'}">
                淨現金流: ${s.net_cashflow >= 0 ? '+' : ''}${s.net_cashflow.toLocaleString()}
            </span>
        `;

        tbody.innerHTML = data.data.map(t => {
            const actionClass = t.action === 'buy' ? 'up' : 'down';
            const actionText = t.action === 'buy' ? '買入' : '賣出';
            const timeStr = t.traded_at ? t.traded_at.split(' ')[1]?.substring(0, 5) || t.traded_at : '--';
            return `<tr>
                <td>${timeStr}</td>
                <td class="${actionClass}" style="font-weight:600;">${actionText}${t.is_odd_lot ? '(零股)' : ''}</td>
                <td>${t.stock_id}</td>
                <td>${t.stock_name || ''}</td>
                <td>${t.shares.toLocaleString()}</td>
                <td class="price">${t.price.toFixed(2)}</td>
                <td>${t.total_amount.toLocaleString()}</td>
                <td>${t.fee.toLocaleString()}</td>
                <td>${t.tax.toLocaleString()}</td>
                <td style="font-weight:600;">${t.net_amount.toLocaleString()}</td>
                <td style="color: var(--text-muted); font-size:12px;">${t.note || ''}</td>
            </tr>`;
        }).join('');

    } catch (e) {
        console.error('載入交易紀錄失敗:', e);
    }
}

// ==========================================
// 法人籌碼
// ==========================================
async function loadInstitutional() {
    try {
        // 大盤法人
        const marketData = await api('/api/institutional/market');
        if (marketData.data) {
            const d = marketData.data;
            setInstValue('inst-foreign', d.foreign_net, '億');
            setInstValue('inst-trust', d.trust_net, '億');
            setInstValue('inst-dealer', d.dealer_net, '億');
            setInstValue('inst-total', d.total_net, '億');
            document.getElementById('inst-date').textContent = `資料日期: ${d.date}`;
        }

        // 個股法人
        const stockData = await api('/api/institutional/stocks');
        const tbody = document.getElementById('stock-inst-body');

        if (stockData.data && stockData.data.length) {
            tbody.innerHTML = stockData.data.map(item => {
                return `<tr>
                    <td>${item.stock_id}</td>
                    <td>${item.stock_name || ''}</td>
                    <td class="${item.foreign_net >= 0 ? 'up' : 'down'}">${formatInst(item.foreign_net)}</td>
                    <td class="${item.trust_net >= 0 ? 'up' : 'down'}">${formatInst(item.trust_net)}</td>
                    <td class="${item.dealer_net >= 0 ? 'up' : 'down'}">${formatInst(item.dealer_net)}</td>
                    <td class="${item.total_net >= 0 ? 'up' : 'down'}" style="font-weight:700;">${formatInst(item.total_net)}</td>
                </tr>`;
            }).join('');
        }
    } catch (e) {
        console.error('載入法人籌碼失敗:', e);
    }
}

function setInstValue(elementId, value, unit) {
    const el = document.getElementById(elementId);
    const sign = value >= 0 ? '+' : '';
    el.textContent = `${sign}${value.toFixed(2)}${unit}`;
    el.style.color = value >= 0 ? 'var(--accent-red)' : 'var(--accent-green)';
}

function formatInst(value) {
    if (value === 0) return '0';
    const sign = value > 0 ? '+' : '';
    if (Math.abs(value) >= 1000) {
        return sign + (value / 1000).toFixed(1) + 'K';
    }
    return sign + value.toLocaleString();
}

async function fetchInstitutional() {
    try {
        showToast('正在抓取法人資料...', 'info');
        await api('/api/institutional/fetch', { method: 'POST' });
        showToast('法人資料已更新', 'success');
        loadInstitutional();
    } catch (e) {
        showToast('抓取失敗: ' + e.message, 'error');
    }
}

// ==========================================
// 每日日記
// ==========================================
async function loadDiary() {
    const dateStr = document.getElementById('diary-date')?.value || new Date().toISOString().split('T')[0];

    try {
        const data = await api(`/api/diary/?date_str=${dateStr}`);

        if (data.data) {
            const d = data.data;
            document.getElementById('diary-ai-review').textContent = d.ai_review || '尚無 AI 檢討。盤後會自動生成。';
            document.getElementById('diary-user-notes').value = d.user_notes || '';
            document.getElementById('diary-reminders').value = d.reminders || '';
            document.getElementById('diary-tomorrow-plan').value = d.tomorrow_plan || '';

            // 情緒標記
            if (d.emotion_tag) {
                selectedEmotion = d.emotion_tag;
                document.querySelectorAll('.emotion-tag').forEach(btn => {
                    btn.classList.toggle('selected', btn.dataset.tag === d.emotion_tag);
                });
            }
        } else {
            document.getElementById('diary-ai-review').textContent = '尚無 AI 檢討。盤後會自動生成。';
            document.getElementById('diary-user-notes').value = '';
            document.getElementById('diary-reminders').value = '';
            document.getElementById('diary-tomorrow-plan').value = '';
            selectedEmotion = '';
            document.querySelectorAll('.emotion-tag').forEach(btn => btn.classList.remove('selected'));
        }
    } catch (e) {
        console.error('載入日記失敗:', e);
    }
}

function selectEmotion(btn) {
    document.querySelectorAll('.emotion-tag').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    selectedEmotion = btn.dataset.tag;
}

async function saveDiary() {
    const dateStr = document.getElementById('diary-date')?.value || new Date().toISOString().split('T')[0];

    try {
        await api(`/api/diary/save?date_str=${dateStr}`, {
            method: 'POST',
            body: JSON.stringify({
                user_notes: document.getElementById('diary-user-notes').value,
                reminders: document.getElementById('diary-reminders').value,
                emotion_tag: selectedEmotion,
                tomorrow_plan: document.getElementById('diary-tomorrow-plan').value
            })
        });
        showToast('日記已儲存', 'success');
    } catch (e) {
        showToast('儲存失敗: ' + e.message, 'error');
    }
}


// ==========================================
// AI 推薦
// ==========================================
async function runAIRecommend() {
    const loading = document.getElementById('ai-loading');
    const result = document.getElementById('ai-recommend-result');
    loading.style.display = 'block';
    result.innerHTML = '';

    try {
        const data = await api('/api/ai/recommend', { method: 'POST' });
        loading.style.display = 'none';

        if (data.data && data.data.recommendations && data.data.recommendations.length) {
            const recs = data.data.recommendations;
            result.innerHTML = `
                <div style="margin-bottom: 16px; padding: 12px; background: var(--bg-primary); border-radius: 8px;">
                    <strong>盤勢觀點：</strong> ${data.data.market_outlook || ''}
                </div>
                ${recs.map(r => {
                    const cur = r.current_price || 0;
                    const tgt = r.target_price || 0;
                    const sl = r.stop_loss_price || 0;
                    const upsidePct = (cur > 0 && tgt > 0) ? ((tgt - cur) / cur * 100).toFixed(1) : null;
                    const downsidePct = (cur > 0 && sl > 0) ? ((sl - cur) / cur * 100).toFixed(1) : null;
                    return `
                    <div class="portfolio-card" style="margin-bottom: 12px;">
                        <div class="stock-header">
                            <div>
                                <div class="stock-name">${r.stock_id} ${r.stock_name}</div>
                            </div>
                            <div style="text-align: right;">
                                ${cur ? `<div class="price" style="font-size:20px;">${cur}</div><div style="font-size:11px; color: var(--text-muted);">目前股價</div>` : ''}
                            </div>
                        </div>
                        <!-- 價位比較列 -->
                        <div style="display:flex; gap:12px; margin: 10px 0; padding: 10px; background: var(--bg-primary); border-radius: 8px;">
                            <div style="flex:1; text-align:center;">
                                <div style="font-size:11px; color: var(--text-muted);">停損價</div>
                                <div style="font-size:16px; font-weight:600; color: var(--accent-green);">${sl || '--'}</div>
                                ${downsidePct !== null ? `<div style="font-size:11px; color: var(--accent-green);">${downsidePct}%</div>` : ''}
                            </div>
                            <div style="flex:1; text-align:center; border-left: 1px solid var(--border-color); border-right: 1px solid var(--border-color);">
                                <div style="font-size:11px; color: var(--text-muted);">現價</div>
                                <div style="font-size:16px; font-weight:700; color: var(--accent-blue);">${cur || '--'}</div>
                            </div>
                            <div style="flex:1; text-align:center;">
                                <div style="font-size:11px; color: var(--text-muted);">目標價</div>
                                <div style="font-size:16px; font-weight:600; color: var(--accent-red);">${tgt || '--'}</div>
                                ${upsidePct !== null ? `<div style="font-size:11px; color: var(--accent-red);">+${upsidePct}%</div>` : ''}
                            </div>
                        </div>
                        <div class="profit-row">
                            <span class="profit-label">推薦理由</span>
                            <span style="font-size:13px;">${r.reason || ''}</span>
                        </div>
                        <div class="profit-row">
                            <span class="profit-label">獲利空間</span>
                            <span style="color: var(--accent-red);">${r.profit_potential || ''}</span>
                        </div>
                        <div class="profit-row">
                            <span class="profit-label">觀察週期</span>
                            <span>${r.time_horizon || ''}</span>
                        </div>
                        ${r.risk ? `<div class="profit-row"><span class="profit-label">風險提示</span><span style="color: var(--accent-yellow);">${r.risk}</span></div>` : ''}
                    </div>
                `}).join('')}
            `;
        } else if (data.data && data.data.market_outlook) {
            // raw text response
            result.innerHTML = `<div class="diary-ai-content">${data.data.market_outlook}</div>`;
        } else {
            result.innerHTML = '<div style="color: var(--text-muted);">AI 未回傳推薦結果，請稍後再試。</div>';
        }

        showToast('AI 分析完成', 'success');
    } catch (e) {
        loading.style.display = 'none';
        result.innerHTML = `<div style="color: var(--accent-red);">分析失敗: ${e.message}</div>`;
        showToast('AI 分析失敗', 'error');
    }
}

async function runAIReview() {
    const result = document.getElementById('ai-review-result');
    result.textContent = 'AI 正在生成檢討報告...';

    try {
        const data = await api('/api/ai/review', { method: 'POST' });
        result.textContent = data.review || '生成完成，但無內容。';
        showToast('AI 檢討已生成', 'success');
    } catch (e) {
        result.textContent = '生成失敗: ' + e.message;
        showToast('AI 檢討失敗', 'error');
    }
}

// ==========================================
// 融資融券
// ==========================================
async function loadMarginData() {
    try {
        const data = await api('/api/margin/');
        const tbody = document.getElementById('margin-table-body');

        if (data.data && data.data.length) {
            tbody.innerHTML = data.data.map(m => `
                <tr>
                    <td>${m.stock_id}</td>
                    <td class="${m.margin_buy > m.margin_sell ? 'up' : 'down'}">${m.margin_buy.toLocaleString()}</td>
                    <td>${m.margin_sell.toLocaleString()}</td>
                    <td>${m.margin_balance.toLocaleString()}</td>
                    <td>${m.short_buy.toLocaleString()}</td>
                    <td class="${m.short_sell > m.short_buy ? 'up' : 'down'}">${m.short_sell.toLocaleString()}</td>
                    <td>${m.short_balance.toLocaleString()}</td>
                    <td style="font-weight:600; ${m.day_trade_ratio > 30 ? 'color: var(--accent-red);' : ''}">${m.day_trade_ratio.toFixed(1)}%</td>
                </tr>
            `).join('');
        }
    } catch (e) {
        console.error('載入融資融券失敗:', e);
    }
}

async function fetchMarginData() {
    try {
        showToast('正在抓取融資融券...', 'info');
        await api('/api/margin/fetch', { method: 'POST' });
        showToast('融資融券資料已更新', 'success');
        loadMarginData();
    } catch (e) {
        showToast('抓取失敗: ' + e.message, 'error');
    }
}

// ==========================================
// 到價提醒
// ==========================================
async function addAlert() {
    const stockId = document.getElementById('alert-stock-id').value.trim();
    const alertType = document.getElementById('alert-type').value;
    const targetPrice = parseFloat(document.getElementById('alert-target-price').value);

    if (!stockId || !targetPrice) {
        showToast('請填寫股票代號和目標價', 'error');
        return;
    }

    try {
        const data = await api('/api/alert/add', {
            method: 'POST',
            body: JSON.stringify({ stock_id: stockId, alert_type: alertType, target_price: targetPrice })
        });
        showToast(data.message, 'success');
        document.getElementById('alert-stock-id').value = '';
        document.getElementById('alert-target-price').value = '';
        loadAlerts();
    } catch (e) {
        showToast('新增提醒失敗: ' + e.message, 'error');
    }
}

async function loadAlerts() {
    try {
        const data = await api('/api/alert/list');
        const activeBody = document.getElementById('active-alerts-body');
        const triggeredBody = document.getElementById('triggered-alerts-body');

        const active = data.data.filter(a => !a.is_triggered);
        const triggered = data.data.filter(a => a.is_triggered);

        if (active.length) {
            activeBody.innerHTML = active.map(a => {
                const typeText = a.alert_type === 'above' ? '突破 >=' : '跌破 <=';
                return `<tr>
                    <td>${a.stock_id}</td>
                    <td>${a.stock_name || ''}</td>
                    <td>${typeText}</td>
                    <td class="price">${a.target_price}</td>
                    <td style="font-size:12px;">${a.created_at || ''}</td>
                    <td><button class="btn btn-danger btn-sm" onclick="deleteAlert(${a.id})">刪除</button></td>
                </tr>`;
            }).join('');
        } else {
            activeBody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--text-muted);">尚無進行中的提醒</td></tr>';
        }

        if (triggered.length) {
            triggeredBody.innerHTML = triggered.map(a => {
                const typeText = a.alert_type === 'above' ? '突破' : '跌破';
                return `<tr>
                    <td>${a.stock_id}</td>
                    <td>${a.stock_name || ''}</td>
                    <td style="color: var(--accent-yellow);">${typeText}</td>
                    <td class="price">${a.target_price}</td>
                    <td style="font-size:12px;">${a.triggered_at || ''}</td>
                </tr>`;
            }).join('');
        } else {
            triggeredBody.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--text-muted);">尚無觸發紀錄</td></tr>';
        }
    } catch (e) {
        console.error('載入提醒失敗:', e);
    }
}

async function deleteAlert(alertId) {
    if (!confirm('確定刪除此提醒？')) return;
    try {
        await api(`/api/alert/delete/${alertId}`, { method: 'DELETE' });
        showToast('提醒已刪除', 'info');
        loadAlerts();
    } catch (e) {
        showToast('刪除失敗', 'error');
    }
}

async function checkAlerts() {
    try {
        const data = await api('/api/alert/check', { method: 'POST' });
        if (data.triggered && data.triggered.length) {
            data.triggered.forEach(t => {
                showToast(t.message, 'success');
            });
            loadAlerts();
        } else {
            showToast('目前無觸發的提醒', 'info');
        }
    } catch (e) {
        showToast('檢查失敗', 'error');
    }
}

async function pollAlertTriggers() {
    try {
        const data = await api('/api/alert/triggered');
        if (data.data && data.data.length) {
            data.data.forEach(t => {
                showToast(t.message, 'success');
                // 嘗試瀏覽器推播
                if (Notification.permission === 'granted') {
                    new Notification('到價提醒', { body: t.message, icon: '/static/favicon.ico' });
                }
            });
            if (currentTab === 'alerts') loadAlerts();
        }
    } catch (e) {
        // 靜默處理
    }
}

// 請求瀏覽器通知權限
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}


// ==========================================
// 績效總覽
// ==========================================

async function loadPerfSummary() {
    try {
        const data = await api('/api/performance/summary');
        const d = data.data;
        const pnlEl = document.getElementById('perf-total-pnl');
        pnlEl.textContent = (d.total_realized_pnl >= 0 ? '+' : '') + d.total_realized_pnl.toLocaleString();
        pnlEl.style.color = d.total_realized_pnl >= 0 ? 'var(--accent-red)' : 'var(--accent-green)';
        document.getElementById('perf-total-trades').textContent = d.total_trades.toLocaleString();
        document.getElementById('perf-total-cost').textContent = d.total_cost.toLocaleString();
    } catch (e) {
        console.error('績效摘要載入失敗:', e);
    }
}

async function loadDailyPnl() {
    const months = document.getElementById('perf-months')?.value || 3;
    try {
        const data = await api(`/api/performance/daily-pnl?months=${months}`);
        const items = data.data;

        const canvas = document.getElementById('pnl-chart');
        const emptyDiv = document.getElementById('pnl-chart-empty');

        if (!items.length) {
            canvas.style.display = 'none';
            emptyDiv.style.display = 'block';
            return;
        }
        canvas.style.display = 'block';
        emptyDiv.style.display = 'none';

        drawPnlChart(canvas, items);
    } catch (e) {
        console.error('損益曲線載入失敗:', e);
    }
}

function drawPnlChart(canvas, items) {
    const ctx = canvas.getContext('2d');
    const W = canvas.parentElement.clientWidth - 40;
    const H = 260;
    canvas.width = W;
    canvas.height = H;

    const pad = { top: 20, right: 20, bottom: 40, left: 70 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    const values = items.map(d => d.cumulative_pnl);
    const maxV = Math.max(...values, 0);
    const minV = Math.min(...values, 0);
    const range = maxV - minV || 1;

    const toX = (i) => pad.left + (i / (items.length - 1 || 1)) * chartW;
    const toY = (v) => pad.top + chartH - ((v - minV) / range) * chartH;

    // 零線
    const zeroY = toY(0);
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(pad.left, zeroY);
    ctx.lineTo(W - pad.right, zeroY);
    ctx.stroke();
    ctx.setLineDash([]);

    // 填充漸層
    const grad = ctx.createLinearGradient(0, pad.top, 0, H - pad.bottom);
    const lastVal = values[values.length - 1];
    if (lastVal >= 0) {
        grad.addColorStop(0, 'rgba(255, 23, 68, 0.3)');
        grad.addColorStop(1, 'rgba(255, 23, 68, 0)');
    } else {
        grad.addColorStop(0, 'rgba(0, 200, 83, 0)');
        grad.addColorStop(1, 'rgba(0, 200, 83, 0.3)');
    }

    ctx.beginPath();
    ctx.moveTo(toX(0), zeroY);
    items.forEach((d, i) => ctx.lineTo(toX(i), toY(d.cumulative_pnl)));
    ctx.lineTo(toX(items.length - 1), zeroY);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // 曲線
    ctx.beginPath();
    items.forEach((d, i) => {
        if (i === 0) ctx.moveTo(toX(i), toY(d.cumulative_pnl));
        else ctx.lineTo(toX(i), toY(d.cumulative_pnl));
    });
    ctx.strokeStyle = lastVal >= 0 ? '#ff1744' : '#00c853';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Y 軸標籤
    ctx.fillStyle = '#6b7280';
    ctx.font = '11px Consolas, monospace';
    ctx.textAlign = 'right';
    const steps = 5;
    for (let i = 0; i <= steps; i++) {
        const v = minV + (range / steps) * i;
        const y = toY(v);
        ctx.fillText((v / 1000).toFixed(0) + 'K', pad.left - 8, y + 4);
    }

    // X 軸日期
    ctx.textAlign = 'center';
    const labelStep = Math.max(1, Math.floor(items.length / 6));
    items.forEach((d, i) => {
        if (i % labelStep === 0 || i === items.length - 1) {
            ctx.fillText(d.date.substring(5), toX(i), H - pad.bottom + 16);
        }
    });

    // 最新值標記
    const lastItem = items[items.length - 1];
    const lx = toX(items.length - 1);
    const ly = toY(lastItem.cumulative_pnl);
    ctx.beginPath();
    ctx.arc(lx, ly, 4, 0, Math.PI * 2);
    ctx.fillStyle = lastVal >= 0 ? '#ff1744' : '#00c853';
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 12px Consolas';
    ctx.textAlign = 'left';
    ctx.fillText((lastVal >= 0 ? '+' : '') + lastVal.toLocaleString(), lx + 8, ly + 4);
}

async function loadMonthlyReport() {
    const monthPicker = document.getElementById('perf-month-picker');
    if (!monthPicker.value) {
        const now = new Date();
        monthPicker.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    }
    const [year, month] = monthPicker.value.split('-').map(Number);

    try {
        const data = await api(`/api/performance/monthly-report?year=${year}&month=${month}`);
        const d = data.data;

        const pnlEl = document.getElementById('month-pnl');
        pnlEl.textContent = (d.net_pnl >= 0 ? '+' : '') + d.net_pnl.toLocaleString();
        pnlEl.style.color = d.net_pnl >= 0 ? 'var(--accent-red)' : 'var(--accent-green)';

        document.getElementById('month-winrate').textContent = d.win_rate + '%';
        document.getElementById('month-active-days').textContent = d.active_days + ' 天';

        document.getElementById('monthly-detail').innerHTML = `
            <div class="perf-stat-row"><span class="label">買入次數</span><span class="value">${d.buy_count}</span></div>
            <div class="perf-stat-row"><span class="label">賣出次數</span><span class="value">${d.sell_count}</span></div>
            <div class="perf-stat-row"><span class="label">勝 / 敗</span><span class="value">${d.winning_trades} 勝 / ${d.losing_trades} 敗</span></div>
            <div class="perf-stat-row"><span class="label">買入總額</span><span class="value">${d.total_buy.toLocaleString()}</span></div>
            <div class="perf-stat-row"><span class="label">賣出總額</span><span class="value">${d.total_sell.toLocaleString()}</span></div>
            <div class="perf-stat-row"><span class="label">手續費</span><span class="value">${d.total_fee.toLocaleString()}</span></div>
            <div class="perf-stat-row"><span class="label">交易稅</span><span class="value">${d.total_tax.toLocaleString()}</span></div>
            <div class="perf-stat-row"><span class="label">平均每日交易</span><span class="value">${d.avg_trades_per_day} 次</span></div>
        `;
    } catch (e) {
        console.error('月報載入失敗:', e);
    }
}

async function loadPortfolioDist() {
    try {
        const data = await api('/api/performance/portfolio-distribution');
        const items = data.data;
        const emptyDiv = document.getElementById('dist-empty');
        const distDiv = document.getElementById('portfolio-dist');

        if (!items.length) {
            emptyDiv.style.display = 'block';
            distDiv.style.display = 'none';
            return;
        }
        emptyDiv.style.display = 'none';
        distDiv.style.display = 'flex';

        drawPieChart(document.getElementById('dist-chart'), items);

        // 圖例
        const colors = ['#ff1744', '#448aff', '#ffc107', '#00c853', '#7c4dff', '#ff9100'];
        document.getElementById('dist-legend').innerHTML = items.map((item, i) => `
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; font-size:13px;">
                <span style="width:12px;height:12px;border-radius:3px;background:${colors[i % colors.length]};display:inline-block;"></span>
                <span>${item.stock_id} ${item.stock_name}</span>
                <span style="color:var(--text-muted); margin-left: auto;">${item.percent}%</span>
                <span style="font-weight:600;">${item.value.toLocaleString()}</span>
            </div>
        `).join('');
    } catch (e) {
        console.error('持倉分佈載入失敗:', e);
    }
}

function drawPieChart(canvas, items) {
    const ctx = canvas.getContext('2d');
    const size = 200;
    canvas.width = size;
    canvas.height = size;
    const cx = size / 2;
    const cy = size / 2;
    const r = 80;
    const colors = ['#ff1744', '#448aff', '#ffc107', '#00c853', '#7c4dff', '#ff9100'];

    let startAngle = -Math.PI / 2;
    items.forEach((item, i) => {
        const sliceAngle = (item.percent / 100) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, r, startAngle, startAngle + sliceAngle);
        ctx.closePath();
        ctx.fillStyle = colors[i % colors.length];
        ctx.fill();
        startAngle += sliceAngle;
    });

    // 中心挖洞（甜甜圈）
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.55, 0, Math.PI * 2);
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-card').trim();
    ctx.fill();

    // 中心文字
    const total = items.reduce((s, i) => s + i.value, 0);
    ctx.fillStyle = '#e8eaed';
    ctx.font = 'bold 14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(total.toLocaleString(), cx, cy + 5);
}


// ==========================================
// 日曆視圖
// ==========================================

let calendarYear = new Date().getFullYear();
let calendarMonth = new Date().getMonth() + 1;

function calendarNav(delta) {
    calendarMonth += delta;
    if (calendarMonth > 12) { calendarMonth = 1; calendarYear++; }
    if (calendarMonth < 1) { calendarMonth = 12; calendarYear--; }
    loadCalendar();
}

async function loadCalendar() {
    document.getElementById('calendar-month-label').textContent = `${calendarYear} 年 ${calendarMonth} 月`;

    try {
        const data = await api(`/api/performance/calendar?year=${calendarYear}&month=${calendarMonth}`);
        const items = data.data;

        // 建立日期 map
        const dayMap = {};
        items.forEach(d => {
            const dayNum = parseInt(d.date.split('-')[2]);
            dayMap[dayNum] = d;
        });

        // 算出本月第一天是星期幾（0=週日）
        const firstDay = new Date(calendarYear, calendarMonth - 1, 1).getDay();
        // 轉為 Mon=0 格式
        const startOffset = firstDay === 0 ? 6 : firstDay - 1;
        const daysInMonth = new Date(calendarYear, calendarMonth, 0).getDate();
        const today = new Date();
        const isCurrentMonth = today.getFullYear() === calendarYear && today.getMonth() + 1 === calendarMonth;

        let html = '';
        // 空白填充
        for (let i = 0; i < startOffset; i++) {
            html += '<div class="calendar-day empty"></div>';
        }

        // 每日格子
        for (let day = 1; day <= daysInMonth; day++) {
            const d = dayMap[day];
            const isToday = isCurrentMonth && day === today.getDate();
            let cls = 'calendar-day';
            if (isToday) cls += ' today';

            if (d && d.daily_pnl > 0) cls += ' profit';
            else if (d && d.daily_pnl < 0) cls += ' loss';

            const pnlText = d && d.daily_pnl !== 0
                ? `<div class="day-pnl">${d.daily_pnl > 0 ? '+' : ''}${(d.daily_pnl / 1000).toFixed(1)}K</div>`
                : '';

            const tradesText = d && d.trade_count > 0
                ? `<div class="day-trades">${d.trade_count} 筆</div>`
                : '';

            const emotionMap = {
                disciplined: '🎯', calm: '😌', impulsive: '😤', panic: '😰', greedy: '🤑'
            };
            const emotionIcon = d && d.emotion_tag ? (emotionMap[d.emotion_tag] || '') : '';
            const icons = d ? `<div class="day-icons">${emotionIcon}${d.has_ai_review ? '🤖' : ''}${d.has_notes ? '📝' : ''}</div>` : '';

            const dateStr = `${calendarYear}-${String(calendarMonth).padStart(2,'0')}-${String(day).padStart(2,'0')}`;

            html += `
                <div class="${cls}" onclick="calendarDayClick('${dateStr}')">
                    <div class="day-num">${day}</div>
                    ${tradesText}
                    ${pnlText}
                    ${icons}
                </div>
            `;
        }

        document.getElementById('calendar-body').innerHTML = html;

        // 月度統計
        let totalPnl = 0, totalTrades = 0, profitDays = 0, lossDays = 0;
        items.forEach(d => {
            totalPnl += d.daily_pnl;
            totalTrades += d.trade_count;
            if (d.daily_pnl > 0) profitDays++;
            if (d.daily_pnl < 0) lossDays++;
        });

        const summaryEl = document.getElementById('calendar-summary');
        const pnlColor = totalPnl >= 0 ? 'var(--accent-red)' : 'var(--accent-green)';
        summaryEl.innerHTML = `
            <div style="display:flex; gap:24px; flex-wrap:wrap;">
                <span>本月損益: <b style="color:${pnlColor};">${totalPnl >= 0 ? '+' : ''}${totalPnl.toLocaleString()}</b></span>
                <span>交易筆數: <b>${totalTrades}</b></span>
                <span>獲利天數: <b style="color:var(--accent-red);">${profitDays}</b></span>
                <span>虧損天數: <b style="color:var(--accent-green);">${lossDays}</b></span>
            </div>
        `;

    } catch (e) {
        console.error('日曆載入失敗:', e);
    }
}

function calendarDayClick(dateStr) {
    // 跳到日記頁面並載入該日
    document.getElementById('diary-date').value = dateStr;
    showTab('diary');
    // 顯示返回日曆按鈕
    document.getElementById('btn-back-calendar').style.display = 'inline-flex';
    // 手動觸發 sidebar button active
    document.querySelectorAll('.sidebar-nav button').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.includes('日記'));
    });
    loadDiary();
}

function backToCalendar() {
    // 隱藏返回按鈕
    document.getElementById('btn-back-calendar').style.display = 'none';
    // 回到日曆頁
    showTab('calendar');
    document.querySelectorAll('.sidebar-nav button').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.includes('日曆'));
    });
    loadCalendar();
}


// ==========================================
// AI 回測
// ==========================================

async function loadBacktest() {
    try {
        const data = await api('/api/ai/backtest?days=60');
        const s = data.summary;
        const items = data.data;

        // 在 AI 推薦頁底部加入回測區塊
        let container = document.getElementById('ai-backtest-container');
        if (!container) {
            // 動態建立容器
            const aiTab = document.getElementById('tab-ai');
            const div = document.createElement('div');
            div.id = 'ai-backtest-container';
            div.className = 'card';
            aiTab.appendChild(div);
            container = div;
        }

        if (!items.length) {
            container.innerHTML = `
                <div class="card-header"><h2>📊 AI 推薦回測</h2></div>
                <div style="color: var(--text-muted); text-align: center; padding: 20px;">
                    尚無推薦紀錄。使用「啟動 AI 分析」後即會開始追蹤。
                </div>
            `;
            return;
        }

        const statusLabels = {
            hit_target: '<span style="color:var(--accent-red);font-weight:700;">✅ 達標</span>',
            hit_stoploss: '<span style="color:var(--accent-green);font-weight:700;">❌ 停損</span>',
            expired: '<span style="color:var(--text-muted);">⏰ 過期</span>',
            pending: '<span style="color:var(--accent-yellow);">⏳ 觀察中</span>'
        };

        container.innerHTML = `
            <div class="card-header">
                <h2>📊 AI 推薦回測（近 60 天）</h2>
                <span style="font-size: 13px; color: var(--text-muted);">
                    準確率: <b style="color:var(--accent-blue);">${s.accuracy}%</b>
                    (${s.hit_target}達標 / ${s.hit_stoploss}停損 / ${s.pending}觀察中 / ${s.expired}過期)
                </span>
            </div>
            <table class="stock-table">
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>代號</th>
                        <th>名稱</th>
                        <th>目標價</th>
                        <th>停損價</th>
                        <th>現價</th>
                        <th>報酬%</th>
                        <th>狀態</th>
                        <th>週期</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map(r => `
                        <tr>
                            <td style="font-size:12px;">${r.date}</td>
                            <td>${r.stock_id}</td>
                            <td>${r.stock_name}</td>
                            <td class="price">${r.target_price || '--'}</td>
                            <td class="price">${r.stop_loss_price || '--'}</td>
                            <td class="price">${r.current_price || '--'}</td>
                            <td class="${r.pnl_percent >= 0 ? 'up' : 'down'}" style="font-weight:600;">
                                ${r.pnl_percent !== 0 ? (r.pnl_percent > 0 ? '+' : '') + r.pnl_percent + '%' : '--'}
                            </td>
                            <td>${statusLabels[r.status] || r.status}</td>
                            <td style="font-size:12px; color:var(--text-muted);">${r.time_horizon}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {
        console.error('回測載入失敗:', e);
    }
}


// ==========================================
// 設定頁面
// ==========================================

async function loadSettings() {
    try {
        const data = await api('/api/settings/');
        const d = data.data;

        // Telegram
        const tgStatus = document.getElementById('tg-bot-status');
        if (d.telegram.bot_token_set) {
            tgStatus.innerHTML = `✅ Bot: <b>@${d.telegram.bot_username}</b> | Chat ID: ${d.telegram.chat_id || '<span style="color:var(--accent-yellow);">未設定</span>'}`;
        } else {
            tgStatus.innerHTML = '❌ Bot Token 未設定（請在 .env 中設定 TELEGRAM_BOT_TOKEN）';
        }
        document.getElementById('settings-tg-chat-id').value = d.telegram.chat_id || '';

        // 交易費用
        document.getElementById('settings-fee-rate').value = (d.trading.broker_fee_rate * 100).toFixed(4) + '%';
        document.getElementById('settings-fee-discount').value = d.trading.broker_fee_discount;
        document.getElementById('settings-tax-stock').value = (d.trading.tax_rate_stock * 100).toFixed(1) + '%';
        document.getElementById('settings-tax-etf').value = (d.trading.tax_rate_etf * 100).toFixed(1) + '%';

        // AI
        document.getElementById('settings-ai-provider').value = d.ai.provider;
    } catch (e) {
        console.error('設定載入失敗:', e);
    }
}

async function detectTgChatId() {
    try {
        showToast('正在偵測 Chat ID，請確認已對 Bot 發送訊息...', 'info');
        const data = await api('/api/settings/telegram/detect', { method: 'POST' });
        document.getElementById('settings-tg-chat-id').value = data.data.chat_id;
        showToast(`偵測成功！Chat ID: ${data.data.chat_id} (${data.data.name})`, 'success');
    } catch (e) {
        showToast('偵測失敗: ' + e.message + '。請先對你的 Telegram Bot 發送任意訊息再重試。', 'error');
    }
}

async function saveTgChatId() {
    const chatId = document.getElementById('settings-tg-chat-id').value.trim();
    if (!chatId) {
        showToast('請輸入 Chat ID', 'error');
        return;
    }
    try {
        await api(`/api/settings/telegram/set-chat-id?chat_id=${chatId}`, { method: 'POST' });
        showToast('Chat ID 已儲存', 'success');
        loadSettings();
    } catch (e) {
        showToast('儲存失敗: ' + e.message, 'error');
    }
}

async function testTelegram() {
    const resultEl = document.getElementById('tg-test-result');
    resultEl.textContent = '發送中...';
    resultEl.style.color = 'var(--text-muted)';
    try {
        await api('/api/settings/telegram/test', { method: 'POST' });
        resultEl.textContent = '✅ 測試訊息已發送！請查看 Telegram';
        resultEl.style.color = 'var(--accent-green)';
    } catch (e) {
        resultEl.textContent = '❌ ' + e.message;
        resultEl.style.color = 'var(--accent-red)';
    }
}

async function saveFeeDiscount() {
    const discount = document.getElementById('settings-fee-discount').value;
    try {
        await api('/api/settings/update', {
            method: 'POST',
            body: JSON.stringify({ key: 'broker_fee_discount', value: discount })
        });
        showToast('手續費折扣已更新', 'success');
    } catch (e) {
        showToast('儲存失敗: ' + e.message, 'error');
    }
}

async function saveAiProvider() {
    const provider = document.getElementById('settings-ai-provider').value;
    try {
        await api('/api/settings/update', {
            method: 'POST',
            body: JSON.stringify({ key: 'ai_provider', value: provider })
        });
        showToast('AI 模型已更新', 'success');
    } catch (e) {
        showToast('儲存失敗: ' + e.message, 'error');
    }
}


// ==========================================
// 集保大戶
// ==========================================

async function fetchTdccData() {
    try {
        showToast('正在抓取集保資料（可能需要 30 秒）...', 'info');
        const data = await api('/api/tdcc/fetch', { method: 'POST' });
        showToast(data.message, 'success');
        loadTdccData();
    } catch (e) {
        showToast('抓取失敗: ' + e.message, 'error');
    }
}

async function loadTdccData() {
    try {
        const data = await api('/api/tdcc/');
        const tbody = document.getElementById('tdcc-table-body');

        if (!data.data || !data.data.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--text-muted);">尚無資料，請點擊「手動抓取」</td></tr>';
            return;
        }

        tbody.innerHTML = data.data.map(item => {
            const s = item.summary;
            if (!s) return '';
            return `<tr>
                <td>${item.stock_id}</td>
                <td>${item.stock_name || ''}</td>
                <td>${s.retail_percent}%</td>
                <td>${s.medium_percent}%</td>
                <td style="font-weight:700; color: ${s.big_percent > 50 ? 'var(--accent-red)' : 'var(--text-primary)'};">${s.big_percent}%</td>
                <td style="font-size:12px; color: var(--text-muted);">${item.date || ''}</td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error('集保資料載入失敗:', e);
    }
}
