import os
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

twelve_symbols = {
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
}

yf_symbols = {
    "XAUUSD": "GC=F", "SPX": "ES=F", "DAX": "^GDAXI",
}

yf_hourly_targets = ["XAUUSD", "SPX", "DAX"]
CSV_PATH = os.path.join("data", "raw_hourly_history.csv")

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"❌ Core database file not found at {CSV_PATH}. Run the initial seed script first.")

# Load core database
master_df = pd.read_csv(CSV_PATH)
new_rows = []

print(f" Starting Hourly Delta Ingestion Loop at {datetime.now()}")

# ==========================================
# 1. FETCH HOURLY FOREX DELTA (Twelve Data)
# ==========================================
if API_KEY and not API_KEY.startswith("YOUR"):
    for name, ticker in twelve_symbols.items():
        url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=100&apikey={API_KEY}"
        try:
            response = requests.get(url, timeout=10).json()
            if "values" in response:
                for bar in response["values"]:
                    row = {
                        'DateTime': str(pd.to_datetime(bar['datetime'])),
                        'Open': float(bar['open']),
                        'High': float(bar['high']),
                        'Low': float(bar['low']),
                        'Close': float(bar['close']),
                        'Instrument': name,
                        'TimeFrame': '1h',
                        'Source': 'TwelveData'
                    }
                    new_rows.append(row)
                print(f"✅ Buffered Twelve Data rows for {name}")
        except Exception as e:
            print(f"❌ Failed Twelve Data delta for {name}: {e}")
else:
    print("协作提示: Skipping Twelve Data (No API key).")

# ==========================================
# 2. FETCH HOURLY INDICES & GOLD DELTA (yfinance)
# ==========================================
for asset_name in yf_hourly_targets:
    ticker = yf_symbols[asset_name]
    try:
        # Mirroring seed configuration perfectly
        df = yf.download(ticker, period="7d", interval="1h", auto_adjust=False, progress=False, threads=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df.index.name = "DateTime"
            df = df.reset_index()
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
            
            for _, idx_row in df.iterrows():
                row = {
                    'DateTime': str(pd.to_datetime(idx_row['DateTime']).tz_localize(None)),
                    'Open': float(idx_row['Open']),
                    'High': float(idx_row['High']),
                    'Low': float(idx_row['Low']),
                    'Close': float(idx_row['Close']),
                    'Instrument': asset_name,
                    'TimeFrame': '1h',
                    'Source': 'yfinance'
                }
                new_rows.append(row)
            print(f"✅ Buffered yfinance hourly delta for {asset_name}")
    except Exception as e:
        print(f"❌ Failed hourly yfinance delta for {asset_name}: {e}")

# ==========================================
# 3. CONCATENATE, DEDUPLICATE & WRITE OUT
# ==========================================
if new_rows:
    delta_df = pd.DataFrame(new_rows)
    
    # Standardize timestamp text styling to guarantee exact merge compatibility
    master_df['DateTime'] = pd.to_datetime(master_df['DateTime'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
    delta_df['DateTime'] = pd.to_datetime(delta_df['DateTime'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Cast matching data types
    for target_df in [master_df, delta_df]:
        target_df['Open'] = target_df['Open'].astype(float)
        target_df['High'] = target_df['High'].astype(float)
        target_df['Low'] = target_df['Low'].astype(float)
        target_df['Close'] = target_df['Close'].astype(float)
        target_df['Instrument'] = target_df['Instrument'].astype(str)
        target_df['TimeFrame'] = target_df['TimeFrame'].astype(str)

    # Append frames together
    combined_df = pd.concat([master_df, delta_df], ignore_index=True)
    combined_df = combined_df.dropna(subset=["DateTime", "Open", "Close"])
    
    # Drop structural duplicates cleanly
    combined_df = combined_df.drop_duplicates(subset=['Instrument', 'TimeFrame', 'DateTime'], keep='last')
    combined_df = combined_df.sort_values(['Instrument', 'TimeFrame', 'DateTime'])
    
    # Flush directly back to Git file layout
    combined_df.to_csv(CSV_PATH, index=False)
    print(f"\n🚀 SUCCESS: Delta layers merged. Total archive expanded to {len(combined_df)} rows.")
else:
    print("\n⚠️ Ingestion cycle completed with no new unique entries discovered.")
