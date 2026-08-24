import os
import sys
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf

# =====================
# 1. MARKET HOLIDAY CHECK
# =====================
def is_nse_market_open_today():
    """Checks if today is an active trading day on NSE."""
    try:
        nse = mcal.get_calendar("NSE")
        today_str = datetime.now().strftime("%Y-%m-%d")
        schedule = nse.schedule(start_date=today_str, end_date=today_str)
        return not schedule.empty
    except Exception as e:
        print(f"Warning checking calendar: {e}")
        # Fallback: At least skip Saturday (5) & Sunday (6)
        return datetime.now().weekday() < 5

if not is_nse_market_open_today():
    print(f"⏸️ NSE Market is closed today ({datetime.now().strftime('%Y-%m-%d')}). Exiting script without sending email.")
    sys.exit(0)

print(f"✅ Market is open today ({datetime.now().strftime('%Y-%m-%d')}). Proceeding with analysis...")

# =====================
# 2. CONFIGURATION
# =====================
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# =====================
# 3. LOAD WATCHLIST
# =====================
with open("watchlist.txt", "r") as f:
    WATCHLIST = [line.strip() for line in f if line.strip()]

# =====================
# 4. HELPER: INDEX METRICS
# =====================
def get_index_metrics(ticker_symbol):
    """Fetches today's close, daily change %, and YTD return for a market index."""
    try:
        current_year = datetime.now().year
        start_date = f"{current_year}-01-01"
        data = yf.download(ticker_symbol, start=start_date, auto_adjust=True, progress=False)
        if len(data) >= 2:
            first_close = float(data["Close"].iloc[0].item())
            last_close = float(data["Close"].iloc[-1].item())
            prev_close = float(data["Close"].iloc[-2].item())
            
            ytd = ((last_close - first_close) / first_close) * 100
            day_change = ((last_close - prev_close) / prev_close) * 100
            
            return {
                "close": last_close,
                "day_change": day_change,
                "ytd": ytd
            }
    except Exception as e:
        print(f"Error fetching metrics for {ticker_symbol}: {e}")
    return None

nifty_stats = get_index_metrics("^NSEI")
sensex_stats = get_index_metrics("^BSESN")

# =====================
# 5. SCAN & PROCESS STOCKS
# =====================
exit_stocks = []
fundamentals_data = []
scanned = 0

for symbol in WATCHLIST:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d", auto_adjust=True)

        if len(df) < 50:
            continue

        scanned += 1

        # Technical Indicators (SMA50 & Diff)
        close = float(df["Close"].iloc[-1])
        sma50 = float(df["Close"].rolling(50).mean().iloc[-1])
        diff = ((close - sma50) / sma50) * 100

        # 52-Week Range & Stock YTD
        week_52_high = float(df["Close"].max())
        week_52_low = float(df["Close"].min())
        
        current_year = datetime.now().year
        ytd_df = df[df.index >= f"{current_year}-01-01"]
        if len(ytd_df) >= 2:
            ytd_open = float(ytd_df["Close"].iloc[0])
            stock_ytd = ((close - ytd_open) / ytd_open) * 100
            stock_ytd_str = f"<span style='color: {'#188038' if stock_ytd >= 0 else '#d93025'}; font-weight: bold;'>{stock_ytd:+.2f}%</span>"
        else:
            stock_ytd_str = "N/A"

        # Check SMA50 Exit
        stock_info = (
            f"<b>{symbol}</b><br>"
            f"Close: ₹{close:.2f} | SMA50: ₹{sma50:.2f} | Diff: <span style='color: #d93025; font-weight: bold;'>{diff:.2f}%</span>"
        )
        if close < sma50:
            exit_stocks.append((diff, stock_info))

        # Fundamentals & Analyst Target
        info = ticker.info or {}
        eps_ttm = info.get("trailingEps")
        eps_str = f"₹{eps_ttm:.2f}" if eps_ttm is not None else "N/A"

        target_price = info.get("targetMeanPrice")
        if target_price:
            target_diff = ((target_price - close) / close) * 100
            target_str = f"₹{target_price:.2f} ({target_diff:+.2f}%)"
        else:
            target_str = "N/A"

        # Next Earnings Date
        next_earnings_str = "N/A"
        try:
            cal = ticker.calendar
            if cal is not None and not (isinstance(cal, pd.DataFrame) and cal.empty):
                if isinstance(cal, dict):
                    earnings_val = cal.get("Earnings Date")
                    if earnings_val:
                        if isinstance(earnings_val, list) and len(earnings_val) > 0:
                            next_earnings_str = pd.to_datetime(earnings_val[0]).strftime('%Y-%m-%d')
                        else:
                            next_earnings_str = str(earnings_val)
                elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                    next_earnings_str = str(cal.loc["Earnings Date"].iloc[0])[:10]
        except Exception:
            pass

        # Last 3 Quarters Beat/Miss History
        quarter_beat_miss = []
        try:
            earn_hist = ticker.earnings_history
            if earn_hist is not None and not earn_hist.empty:
                recent_quarters = earn_hist.tail(3)
                for idx, row in recent_quarters.iterrows():
                    eps_act = row.get("epsActual")
                    eps_est = row.get("epsEstimate")
                    q_period = str(idx)[:10] if not isinstance(idx, int) else row.get("quarter", "Q")

                    if pd.notna(eps_act) and pd.notna(eps_est):
                        diff_val = eps_act - eps_est
                        status = "✅ Beat" if diff_val >= 0 else "❌ Miss"
                        quarter_beat_miss.append(f"{q_period}: {status} (Act: {eps_act:.2f} vs Est: {eps_est:.2f})")
                    elif pd.notna(eps_act):
                        quarter_beat_miss.append(f"{q_period}: Act: {eps_act:.2f}")
        except Exception:
            pass

        quarters_summary = " | ".join(quarter_beat_miss) if quarter_beat_miss else "No consensus/history data"

        # Corporate Actions
        actions = ticker.actions.tail(2)
        action_summary = "None"
        if not actions.empty:
            action_lines = []
            for date, row in actions.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                if row.get("Dividends", 0) > 0:
                    action_lines.append(f"Div: ₹{row['Dividends']:.2f} ({date_str})")
                if row.get("Stock Splits", 0) > 0:
                    action_lines.append(f"Split: {row['Stock Splits']} ({date_str})")
            if action_lines:
                action_summary = ", ".join(action_lines)

        # Quarterly Results (Revenue & PAT)
        q_inc = ticker.quarterly_income_stmt
        fin_summary = "N/A"
        if not q_inc.empty:
            latest_q_date = q_inc.columns[0].strftime("%b %Y")
            rev = q_inc.loc["Total Revenue"].iloc[0] if "Total Revenue" in q_inc.index else None
            pat = q_inc.loc["Net Income"].iloc[0] if "Net Income" in q_inc.index else None

            rev_str = f"₹{rev/1e7:.2f} Cr" if rev and pd.notna(rev) else "N/A"
            pat_str = f"₹{pat/1e7:.2f} Cr" if pat and pd.notna(pat) else "N/A"
            fin_summary = f"{latest_q_date} -> Rev: {rev_str}, PAT: {pat_str}"

        # Card Layout
        fundamentals_data.append(f"""
        <div style="border-bottom: 1px solid #e0e0e0; padding-bottom: 12px; margin-bottom: 12px;">
            <div style="font-size: 16px; font-weight: bold; color: #1a73e8; margin-bottom: 4px;">{symbol}</div>
            <table style="width: 100%; font-size: 13px; line-height: 1.6; border-collapse: collapse;">
                <tr>
                    <td style="width: 50%;"><b>Close:</b> ₹{close:.2f} | <b>YTD:</b> {stock_ytd_str}</td>
                    <td style="width: 50%;"><b>52W Range:</b> ₹{week_52_low:.2f} – ₹{week_52_high:.2f}</td>
                </tr>
                <tr>
                    <td><b>EPS (TTM):</b> {eps_str}</td>
                    <td><b>1Y Target:</b> {target_str}</td>
                </tr>
                <tr>
                    <td><b>Next Earnings Date:</b> {next_earnings_str}</td>
                    <td><b>Corporate Actions:</b> {action_summary}</td>
                </tr>
                <tr>
                    <td colspan="2"><b>Quarterly Results:</b> {fin_summary}</td>
                </tr>
                <tr>
                    <td colspan="2"><b>Last 3Q Beat/Miss:</b> <span style="font-size: 12px;">{quarters_summary}</span></td>
                </tr>
            </table>
        </div>
        """)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

exit_stocks.sort(key=lambda x: x[0])

# =====================
# 6. FORMAT BENCHMARKS
# =====================
def format_index_cell(name, stats):
    if not stats:
        return f"<div><b>{name}:</b> N/A</div>"
    day_color = "#188038" if stats['day_change'] >= 0 else "#d93025"
    ytd_color = "#188038" if stats['ytd'] >= 0 else "#d93025"
    return f"""
    <div style="flex: 1; background: #ffffff; padding: 10px 14px; border-radius: 6px; border: 1px solid #e0e0e0; margin-right: 8px;">
        <div style="font-size: 13px; color: #5f6368; font-weight: bold;">{name}</div>
        <div style="font-size: 18px; font-weight: bold; margin: 2px 0;">{stats['close']:,.2f}</div>
        <div style="font-size: 12px;">
            Day: <span style="color: {day_color}; font-weight: bold;">{stats['day_change']:+.2f}%</span> | 
            YTD: <span style="color: {ytd_color}; font-weight: bold;">{stats['ytd']:+.2f}%</span>
        </div>
    </div>
    """

nifty_html_box = format_index_cell("🇮🇳 NIFTY 50", nifty_stats)
sensex_html_box = format_index_cell("🏛️ SENSEX", sensex_stats)

# =====================
# 7. BUILD HTML EMAIL
# =====================
if exit_stocks:
    exit_list_html = "<br><hr style='border-top: 1px dashed #ccc;'><br>".join([item[1] for item in exit_stocks])
    exits_content = f"<h3 style='color: #d93025; margin-bottom: 8px;'>🚨 EXITS (Below SMA50)</h3><div>{exit_list_html}</div>"
else:
    exits_content = "<p style='color: #188038; font-weight: bold;'>🎉 All watchlist stocks are trading ABOVE their 50-day SMA.</p>"

fundamentals_html = "".join(fundamentals_data)

html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.5; color: #202124; max-width: 680px; margin: auto; padding: 10px;">
    
    <!-- HEADER -->
    <div style="background-color: #f8f9fa; border: 1px solid #dadce0; padding: 14px; border-radius: 8px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 6px 0; color: #1a73e8; font-size: 20px;">📈 Daily Portfolio & Market Intelligence</h2>
        <div style="font-size: 13px; color: #5f6368;"><b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | <b>Scanned:</b> {scanned} stocks</div>
    </div>

    <!-- TECHNICAL ALERTS (SMA50) -->
    <div style="background-color: #ffffff; border: 1px solid #dadce0; padding: 14px; border-radius: 8px; margin-bottom: 20px;">
        {exits_content}
    </div>

    <!-- BENCHMARK INDEX SECTION -->
    <div style="margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between;">
            {nifty_html_box}
            {sensex_html_box}
        </div>
    </div>

    <!-- FUNDAMENTALS, EPS & EARNINGS -->
    <div style="background-color: #ffffff; border: 1px solid #dadce0; padding: 14px; border-radius: 8px;">
        <h3 style="margin-top: 0; color: #202124; border-bottom: 2px solid #1a73e8; padding-bottom: 6px;">📊 Fundamentals & Earnings Outlook</h3>
        {fundamentals_html if fundamentals_html else '<p>No data retrieved.</p>'}
    </div>

</body>
</html>
"""

# =====================
# 8. SEND EMAIL
# =====================
subject = f"Market Alert: SMA50, Benchmarks & Earnings - {datetime.now().strftime('%Y-%m-%d')}"
email = MIMEText(html_body, "html")
email["Subject"] = subject
email["From"] = EMAIL_ADDRESS
email["To"] = EMAIL_ADDRESS

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(email)
    print("Market intelligence email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
