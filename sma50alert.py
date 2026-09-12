import os
import sys
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf

# =====================
# 1. MARKET HOLIDAY CHECK
# =====================
def is_nse_market_open_today():
    try:
        nse = mcal.get_calendar("NSE")
        today_str = datetime.now().strftime("%Y-%m-%d")
        schedule = nse.schedule(start_date=today_str, end_date=today_str)
        return not schedule.empty
    except Exception as e:
        print(f"Warning checking calendar: {e}")
        return datetime.now().weekday() < 5

if not is_nse_market_open_today():
    print(f"⏸️ NSE Market closed today ({datetime.now().strftime('%Y-%m-%d')}). Exiting.")
    sys.exit(0)

# =====================
# 2. CONFIGURATION & WATCHLIST
# =====================
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

with open("watchlist.txt", "r") as f:
    WATCHLIST = [line.strip() for line in f if line.strip()]

# =====================
# 3. METRICS PULLERS
# =====================
def get_index_metrics(ticker_symbol):
    try:
        current_year = datetime.now().year
        start_date = f"{current_year}-01-01"
        data = yf.download(ticker_symbol, start=start_date, auto_adjust=True, progress=False)
        if len(data) >= 2:
            first_close = float(data["Close"].iloc[0].item())
            last_close = float(data["Close"].iloc[-1].item())
            prev_close = float(data["Close"].iloc[-2].item())
            return {
                "close": last_close,
                "day_change": ((last_close - prev_close) / prev_close) * 100,
                "ytd": ((last_close - first_close) / first_close) * 100
            }
    except Exception as e:
        print(f"Index error {ticker_symbol}: {e}")
    return None

def get_fii_dii_metrics():
    try:
        # URL updated to Mr. Chartist's dedicated open JSON data api endpoint
        url = "https://mrchartist.com"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data:
            return None
        
        fii_net, dii_net = 0.0, 0.0
        if isinstance(data, dict):
            if "cash" in data:
                fii_net = float(data["cash"].get("fii_net", 0.0))
                dii_net = float(data["cash"].get("dii_net", 0.0))
            else:
                fii_net = float(data.get("fii_net", data.get("fiiNet", 0.0)))
                dii_net = float(data.get("dii_net", data.get("diiNet", 0.0)))
        return {"fii": fii_net, "dii": dii_net}
    except Exception as e:
        print(f"⚠️ Failed to get FII/DII data: {e}")
        return None

# Fetch global data blocks
nifty = get_index_metrics("^NSEI")
sensex = get_index_metrics("^BSESN")
fiidii = get_fii_dii_metrics()
# =====================
# 4. PORTFOLIO SCANNER LOOP
# =====================
exit_stocks = []
fundamentals_data = []
scanned = 0

for symbol in WATCHLIST:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d", auto_adjust=True)
        if len(df) < 50: continue
        scanned += 1

        close = float(df["Close"].iloc[-1].item())
        sma50 = float(df["Close"].rolling(50).mean().iloc[-1].item())
        diff = ((close - sma50) / sma50) * 100
        w_high = float(df["Close"].max().item())
        w_low = float(df["Close"].min().item())

        current_year = datetime.now().year
        ytd_df = df[df.index >= f"{current_year}-01-01"]
        stock_ytd = ((close - float(ytd_df["Close"].iloc[0].item())) / float(ytd_df["Close"].iloc[0].item())) * 100 if len(ytd_df) >= 2 else 0.0

        if close < sma50:
            exit_stocks.append(f"<b>{symbol}</b><br>Close: ₹{close:.2f} | SMA50: ₹{sma50:.2f} | Diff: <span style='color: #d93025;'>{diff:.2f}%</span>")

        info = ticker.info or {}
        eps_str = f"₹{info.get('trailingEps'):.2f}" if info.get('trailingEps') else "N/A"
        target_str = f"₹{info.get('targetMeanPrice'):.2f}" if info.get('targetMeanPrice') else "N/A"

        next_earn = "N/A"
        try:
            cal = ticker.calendar
            if cal is not None and not (isinstance(cal, pd.DataFrame) and cal.empty):
                if isinstance(cal, dict) and cal.get("Earnings Date"):
                    next_earn = pd.to_datetime(cal.get("Earnings Date")[0]).strftime('%Y-%m-%d')
                elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                    next_earn = str(cal.loc["Earnings Date"].iloc[0])[:10]
        except: pass

        history_list = []
        try:
            hist = ticker.earnings_history
            if hist is not None and not hist.empty:
                for idx, row in hist.tail(3).iterrows():
                    act, est = row.get("epsActual"), row.get("epsEstimate")
                    if pd.notna(act) and pd.notna(est):
                        history_list.append(f"{str(idx)[:7]}: {'✅' if act>=est else '❌'} ({act:.1f} vs {est:.1f})")
        except: pass
        q_history = " | ".join(history_list) if history_list else "No data"

        fundamentals_data.append({
            "sym": symbol, "close": close, "ytd": stock_ytd, "low": w_low, "high": w_high,
            "eps": eps_str, "target": target_str, "earn": next_earn, "qhist": q_history
        })
    except Exception as e:
        print(f"Skipping {symbol}: {e}")

# =====================
# 5. HTML BUILDER ENGINE
# =====================
def make_box(title, stats):
    if not stats: return f"<div style='flex:1; border:1px solid #e0e0e0; padding:10px;'><b>{title}</b>: N/A</div>"
    c_day = "#188038" if stats['day_change'] >= 0 else "#d93025"
    c_ytd = "#188038" if stats['ytd'] >= 0 else "#d93025"
    return f"""
    <div style="flex:1; background:#fff; padding:10px 14px; border:1px solid #e0e0e0; border-radius:6px; min-width:160px; margin:4px;">
        <div style="font-size:12px; color:#5f6368; font-weight:bold;">{title}</div>
        <div style="font-size:18px; font-weight:bold; margin:2px 0;">{stats['close']:,.2f}</div>
        <div style="font-size:11px;">
            Day: <span style="color:{c_day}; font-weight:bold;">{stats['day_change']:+.2f}%</span> | YTD: <span style="color:{c_ytd}; font-weight:bold;">{stats['ytd']:+.2f}%</span>
        </div>
    </div>"""

def make_fiidii_box(data):
    if not data: return "<div style='flex:1; border:1px solid #e0e0e0; padding:10px; background:#fff; border-radius:6px; margin:4px;'>🏢 Inst. Data Offline</div>"
    f_col = "#188038" if data['fii'] >= 0 else "#d93025"
    d_col = "#188038" if data['dii'] >= 0 else "#d93025"
    return f"""
    <div style="flex:1; background:#fff; padding:10px 14px; border:1px solid #e0e0e0; border-radius:6px; min-width:160px; margin:4px;">
        <div style="font-size:12px; color:#5f6368; font-weight:bold;">🏢 INSTITUTIONAL NET (Cr)</div>
        <div style="font-size:13px; margin-top:4px;">FII Net: <span style="color:{f_col}; font-weight:bold;">{data['fii']:+.2f}</span></div>
        <div style="font-size:13px; margin-top:2px;">DII Net: <span style="color:{d_col}; font-weight:bold;">{data['dii']:+.2f}</span></div>
    </div>"""

exit_box_content = "<br><hr style='border-top:1px dashed #ccc;'><br>".join(exit_stocks) if exit_stocks else "🎉 All watchlist stocks are trading ABOVE their 50-day SMA."

fund_cards = ""
for stock in fundamentals_data:
    col = "#188038" if stock['ytd'] >= 0 else "#d93025"
    fund_cards += f"""
    <div style="border-bottom:1px solid #e0e0e0; padding-bottom:10px; margin-bottom:10px;">
        <div style="font-size:15px; font-weight:bold; color:#1a73e8;">{stock['sym']}</div>
        <table style="width:100%; font-size:12px; line-height:1.5;">
            <tr><td><b>Close:</b> ₹{stock['close']:.2f} (<span style="color:{col}; font-weight:bold;">{stock['ytd']:+.2f}% YTD</span>)</td><td><b>52W Range:</b> ₹{stock['low']:.2f} - ₹{stock['high']:.2f}</td></tr>
            <tr><td><b>EPS (TTM):</b> {stock['eps']}</td><td><b>1Y Target:</b> {stock['target']}</td></tr>
            <tr><td><b>Earnings Date:</b> {stock['earn']}</td><td><b>Last 3Q Beats:</b> {stock['qhist']}</td></tr>
        </table>
    </div>"""

html_body = f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif; color:#202124; max-width:650px; margin:auto; padding:10px;">
    <div style="background:#f8f9fa; border:1px solid #dadce0; padding:12px; border-radius:8px; margin-bottom:15px;">
        <h2 style="margin:0; color:#1a73e8; font-size:18px;">📊 Portfolio Market Intelligence Dashboard</h2>
        <div style="font-size:12px; color:#5f6368;"><b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Scanned {scanned} tickers</div>
    </div>
    <div style="border:1px solid #dadce0; padding:12px; border-radius:8px; margin-bottom:15px;">
        <h3 style="color:#d93025; margin:0 0 6px 0; font-size:14px;">🚨 SMA50 ALERTS</h3>
        <div style="font-size:13px;">{exit_box_content}</div>
    </div>
    <div style="display:flex; flex-wrap:wrap; margin-bottom:15px;">
        {make_box("🇮🇳 NIFTY 50", nifty)}
        {make_box("🏛️ SENSEX", sensex)}
        {make_fiidii_box(fiidii)}
    </div>
    <div style="border:1px solid #dadce0; padding:12px; border-radius:8px; background:#fff;">
        <h3 style="margin:0 0 8px 0; color:#202124; border-bottom:2px solid #1a73e8; padding-bottom:4px; font-size:14px;">📈 Fundamentals Deep Dive</h3>
        {fund_cards if fund_cards else '<p>No data retrieved.</p>'}
    </div>
</body></html>"""

# =====================
# 6. EMAIL TRANSMISSION
# =====================
msg = MIMEText(html_body, "html")
msg["Subject"] = f"Market Scan Dashboard - {datetime.now().strftime('%Y-%m-%d')}"
msg["From"] = EMAIL_ADDRESS
msg["To"] = EMAIL_ADDRESS 

try:
    with smtplib.SMTP_SSL("://gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
    print("Email sent successfully.") 
except Exception as e:
    print(f"Email send failed: {e}")
    sys.exit(1)
