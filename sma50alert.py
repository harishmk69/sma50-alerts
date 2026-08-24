import sys
import pandas_market_calendars as mcal
from datetime import datetime

# =====================
# MARKET HOLIDAY CHECK
# =====================
def is_nse_market_open_today():
    """Checks if today is a valid NSE trading session (excludes weekends & trading holidays)."""
    nse = mcal.get_calendar("NSE")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Fetch valid trading schedule for today
    schedule = nse.schedule(start_date=today_str, end_date=today_str)
    return not schedule.empty

if not is_nse_market_open_today():
    print(f"⏸️ Market is closed today ({datetime.now().strftime('%Y-%m-%d')}). Skipping alert.")
    sys.exit(0)  # Exits gracefully without failing the GitHub Action
