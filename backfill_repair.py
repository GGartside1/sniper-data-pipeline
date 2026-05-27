import os
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from datetime import datetime

# --- CONFIGURATION ---
API_KEY = os.getenv("TWELVE_DATA_API_KEY") 

twelve_symbols = {
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
}

yf_symbols = {
    "XAUUSD": "GC=F", "SPX": "ES=F", "DAX": "^GDAXI"
}

CSV_PATH = os.path.join("data", "raw_hourly_history.csv")

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"❌ Core database file not found at {CSV_PATH}.")

# Load Master History
master_df = pd.read_csv(CSV_PATH)
master_df['DateTime'] = pd.to_datetime(master_df['DateTime'], format='mixed')

new_rows = []

print(f"🧹 Starting One-Off 4-Day Gap Backfill Repair at {datetime.now()}")

# ==========================================
# 1. FETCH MULTI-DAY FOREX BACKFILL (Twelve Data - outputsize=100)
# ==========================================
for name, ticker in twelve_symbols.items():
    # outputsize=100 gives us roughly 4 days of hourly trading data to capture the full gap
    url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=100&apikey={API_KEY}"
    try:
        response = requests.get(url).json()
        if "values" in response and len(response['values']) > 0:
            bars_fetched = 0
            for bar in response['values']:
                row = {
                    'DateTime': pd.to_datetime(bar['datetime']),
                    'Open': float(bar['open']),
                    'High': float(bar['high']),
                    'Low': float(bar['low']),
                    'Close': float(bar['close']),
                    'Instrument': name,
                    'TimeFrame': '1h',
                    'Source': 'TwelveData'
                }
                new_rows.append(row)
                bars_fetched += 1
            print(f"✅ Recovered {bars_fetched} historical hours for TwelveData {name}")
    except Exception as e:
        print(f"❌ Failed backfill for Twelve Data {name}: {e}")

# ==========================================
# 2. FETCH MULTI-DAY INDICES & GOLD BACKFILL (yfinance - period=7d)
# ==========================================
for name, ticker in yf_symbols.items():
    try:
        # Requesting a safe 7-day window to completely cover the weekend and the 4-day dropout gap
        h_df = yf.download(ticker, period="7d", interval="1h", progress=False, group_by="ticker")
        
        if not h_df.empty:
            if isinstance(h_df.columns, pd.MultiIndex):
                if ticker in h_df.columns.levels[0]:
                    h_df = h_df[ticker]
                else:
                    h_df.columns = h_df.columns.get_level_values(0)

            h_df = h_df.dropna(subset=['Close'])
            bars_fetched = 0
            
            for timestamp, bar in h_df.iterrows():
                row = {
                    'DateTime': pd.to_datetime(timestamp).tz_localize(None),
                    'Open': float(bar['Open']),
                    'High': float(bar['High']),
                    'Low': float(bar['Low']),
                    'Close': float(bar['Close']),
                    'Instrument': name,
                    'TimeFrame': '1h',
                    'Source': 'yfinance'
                }
                new_rows.append(row)
                bars_fetched += 1
            print(f"✅ Recovered {bars_fetched} historical hours for yfinance {name}")
    except Exception as e:
        print(f"❌ Failed backfill for yfinance {name}: {e}")

# ==========================================
# 3. MERGE, DEDUPLICATE, AND FLUSH
# ==========================================
if new_rows:
    delta_df = pd.DataFrame(new_rows)
    combined_df = pd.concat([master_df, delta_df], ignore_index=True)
    
    # Force alignment format conversions
    combined_df['DateTime'] = pd.to_datetime(combined_df['DateTime'], format='mixed')
    
    # CRITICAL: Drop duplicates but keep 'last' to let newly recovered data heal the file cleanly
    initial_count = len(combined_df)
    combined_df = combined_df.drop_duplicates(subset=['Instrument', 'TimeFrame', 'DateTime'], keep='last')
    combined_df = combined_df.sort_values(['Instrument', 'TimeFrame', 'DateTime'])
    
    combined_df.to_csv(CSV_PATH, index=False)
    final_count = len(combined_df)
    print(f"\n🚀 REPAIR COMPLETE: Deduplicated and merged. Added {final_count - initial_count + len(delta_df)} missing bars. Database total: {final_count} rows.")
else:
    print("⚠️ No data recovered.")
