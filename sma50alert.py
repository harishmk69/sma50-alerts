import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
import pandas as pd
import yfinance as yf

# =====================
# CONFIGURATION
# =====================
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# =====================
# LOAD WATCHLIST
# =====================
with open("watchlist.txt", "r") as f:
    WATCHLIST = [line.strip() for line in f if line.strip()]

# =====================
# HELPER: INDEX YTD
# =====================
def get_ytd_return(ticker_symbol):
    """Calculates Year-To-Date return using history from Jan 1st of the current year."""
    try:
        current_year = datetime.now().year
        start_date = f"{current_year}-01-01"
        data = yf.download(ticker_symbol, start=start_date, auto_adjust=True, progress=False)
        if len(data) >= 2:
            first_close = float(data["Close"].iloc[0].item())
            last_close = float(data["Close"].iloc[-1].item())
            return ((last_close - first_close) / first_close) * 100
    except Exception as e:
        print(f"Error fetching YTD for {ticker_symbol}: {e}")
    return None

nifty_ytd = get_ytd_return("^NSEI")
sensex_ytd = get_ytd_return("^BSESN")

# =====================
# SCAN & PROCESS STOCKS
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

        # 1. Technical Indicators (SMA50 & Diff)
        close = float(df["Close"].iloc[-1])
        sma50 = float(df["Close"].rolling(50).mean().iloc[-1])
        diff = ((close - sma50) / sma50) * 100

        # 2. 52-Week Range & Stock YTD
        week_52_high = float(df["Close"].max())
        week_52_low = float(df["Close"].min())
        
        # Calculate stock YTD
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

        # 3. Fundamentals & Info Attributes
        info = ticker.info or {}
        eps_ttm = info.get("trailingEps")
        eps_str = f"₹{eps_ttm:.2f}" if eps_ttm is not None else "N/A"

        target_price = info.get("targetMeanPrice")
        if target_price:
            target_diff = ((target_price - close) / close) * 100
            target_str = f"₹{target_price:.2f} ({target_diff:+.2f}%)"
        else:
            target_str = "N/A"

        # 4. Last 3 Quarters (Beat / Miss History)
        quarter_beat_miss = []
        try:
            earn_hist = ticker.earnings_history
            if earn_hist is not None and not earn_hist.empty:
                # Take the most recent 3 quarters
                recent_quarters = earn_hist.tail(3)
                for idx, row in recent_quarters.iterrows():
                    eps_act = row.get("epsActual")
                    eps_est = row.get("epsEstimate")
                    
                    # Format Quarter Date / Period
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

        # 5. Corporate Actions (Recent dividends/splits)
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

        # 6. Quarterly Income Statement (Revenue & PAT)
        q_inc = ticker.quarterly_income_stmt
        fin_summary = "N/A"
        if not q_inc.empty:
            latest_q_date = q_inc.columns[0].strftime("%b %Y")
            rev = q_inc.loc["Total Revenue"].iloc[0] if "Total Revenue" in q_inc.index else None
            pat = q_inc.loc["Net Income"].iloc[0] if "Net Income" in q_inc.index else None

            rev_str = f"₹{rev/1e7:.2f} Cr" if rev and pd.notna(rev) else "N/A"
            pat_str = f"₹{pat/1e7:.2f} Cr" if pat and pd.notna(pat) else "N/A"
            fin_summary = f"{latest_q_date} -> Rev: {rev_str}, PAT: {pat_str}"

        # Combine into card layout
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
                    <td colspan="2"><b>Quarterly Results:</b> {fin_summary}</td>
                </tr>
                <tr>
                    <td colspan="2"><b>Last 3Q Beat/Miss:</b> <span style="font-size: 12px;">{quarters_summary}</span></td>
                </tr>
                <tr>
                    <td colspan="2"><b>Corporate Actions:</b> {action_summary}</td>
                </tr>
            </table>
        </div>
        """)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

exit_stocks.sort(key=lambda x: x[0])

# =====================
# BUILD HTML EMAIL
# =====================
nifty_badge = f"<span style='color: {'#188038' if nifty_ytd and nifty_ytd >= 0 else '#d93025'}; font-weight: bold;'>{nifty_ytd:+.2f}%</span>" if nifty_ytd is not None else "N/A"
sensex_badge = f"<span style='color: {'#188038' if sensex_ytd and sensex_ytd >= 0 else '#d93025'}; font-weight: bold;'>{sensex_ytd:+.2f}%</span>" if sensex_ytd is not None else "N/A"

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
    
    <!-- HEADER & BENCHMARK INDEX RETURNS -->
    <div style="background-color: #f8f9fa; border: 1px solid #dadce0; padding: 14px; border-radius: 8px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 8px 0; color: #1a73e8; font-size: 20px;">📈 Daily Market & Portfolio Intelligence</h2>
        <div style="font-size: 13px; color: #5f6368; margin-bottom: 10px;"><b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | <b>Scanned:</b> {scanned} stocks</div>
        
        <div style="display: flex; background: #ffffff; padding: 8px 12px; border-radius: 6px; border: 1px solid #e8eaed; font-size: 14px;">
            <div style="margin-right: 25px;">🇮🇳 <b>NIFTY 50 YTD:</b> {nifty_badge}</div>
            <div>🏛️ <b>BSE SENSEX YTD:</b> {sensex_badge}</div>
        </div>
    </div>

    <!-- TECHNICAL ALERTS -->
    <div style="background-color: #ffffff; border: 1px solid #dadce0; padding: 14px; border-radius: 8px; margin-bottom: 20px;">
        {exits_content}
    </div>

    <!-- FUNDAMENTALS, EPS & EARNINGS -->
    <div style="background-color: #ffffff; border: 1px solid #dadce0; padding: 14px; border-radius: 8px;">
        <h3 style="margin-top: 0; color: #202124; border-bottom: 2px solid #1a73e8; padding-bottom: 6px;">📊 Fundamentals, Quarterly & 52W Range</h3>
        {fundamentals_html if fundamentals_html else '<p>No data retrieved.</p>'}
    </div>

</body>
</html>
"""

# =====================
# SEND EMAIL
# =====================
subject = f"Market Alert: SMA50 & Deep Fundamentals - {datetime.now().strftime('%Y-%m-%d')}"
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
