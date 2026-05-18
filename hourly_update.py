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

# Ensure our database exists before trying to append to it
if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"❌ Core database file not found at {CSV_PATH}. Please run the initial seed script first.")

# Load existing history to prevent duplicates
master_df = pd.read_csv(CSV_PATH)
master_df['DateTime'] = pd.to_datetime(master_df['DateTime'], format='mixed')

new_rows = []

print(f" Starting Hourly Delta Ingestion Loop at {datetime.now()}")

# ==========================================
# 1. FETCH HOURLY FOREX DELTA (Twelve Data - outputsize=1)
# ==========================================
for name, ticker in twelve_symbols.items():
    url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=1&apikey={API_KEY}"
    try:
        response = requests.get(url).json()
        if "values" in response and len(response['values']) > 0:
            latest_bar = response['values'][0]
            
            # Formulate row dictionary matching master database schema
            row = {
                'DateTime': pd.to_datetime(latest_bar['datetime']),
                'Open': float(latest_bar['open']),
                'High': float(latest_bar['high']),
                'Low': float(latest_bar['low']),
                'Close': float(latest_bar['close']),
                'Instrument': name,
                'TimeFrame': '1h',
                'Source': 'TwelveData'
            }
            new_rows.append(row)
            print(f"✅ Fetched fresh TwelveData bar for {name}: {row['DateTime']}")
        else:
            print(f"⚠️ No active bars returned from Twelve Data for {name}")
    except Exception as e:
        print(f"❌ Failed to fetch hourly delta from Twelve Data for {name}: {e}")

# ==========================================
# 2. FETCH HOURLY INDICES & GOLD DELTA (yfinance - period=1d)
# ==========================================
for name, ticker in yf_symbols.items():
    try:
        # Requesting 1 day of back history to ensure we catch the current hour cleanly
        h_df = yf.download(ticker, period="1d", interval="1h", progress=False)
        if not h_df.empty:
            if isinstance(h_df.columns, pd.MultiIndex):
                h_df.columns = h_df.columns.get_level_values(0)
            h_df = h_df.reset_index().rename(columns={'Datetime': 'DateTime'})
            h_df['DateTime'] = pd.to_datetime(h_df['DateTime']).dt.tz_localize(None)
            
            # Grab just the absolute most recent hour row from the dataframe
            latest_bar = h_df.iloc[-1]
            row = {
                'DateTime': latest_bar['DateTime'],
                'Open': float(latest_bar['Open']),
                'High': float(latest_bar['High']),
                'Low': float(latest_bar['Low']),
                'Close': float(latest_bar['Close']),
                'Instrument': name,
                'TimeFrame': '1h',
                'Source': 'yfinance'
            }
            new_rows.append(row)
            print(f"✅ Fetched fresh yfinance hourly bar for {name}: {row['DateTime']}")
    except Exception as e:
        print(f"❌ Failed to fetch hourly delta from yfinance for {name}: {e}")

# ==========================================
# 3. APPEND, DUPLICATE CHECK, AND FLUSH TO STORAGE
# ==========================================
if new_rows:
    delta_df = pd.DataFrame(new_rows)
    
    # Merge old history with incoming delta data
    combined_df = pd.concat([master_df, delta_df], ignore_index=True)
    
    # Critical step: Drop exact row matches if the cron fires twice within the same hour window
    combined_df = combined_df.drop_duplicates(subset=['Instrument', 'TimeFrame', 'DateTime'], keep='last')
    
    # Maintain strict chronological sequencing for Snowflake/dbt indexing efficiency
    combined_df = combined_df.sort_values(['Instrument', 'TimeFrame', 'DateTime'])
    
    # Save back to repository
    combined_df.to_csv(CSV_PATH, index=False)
    print(f"🚀 SUCCESS: Appended new delta data layer. Database now contains {len(combined_df)} rows.")
else:
    print("⚠️ Process complete: No incremental updates discovered during this window cycle.")
