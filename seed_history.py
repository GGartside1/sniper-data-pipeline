import os
import pandas as pd
import numpy as np
import requests
import time
import yfinance as yf

# --- CONFIGURATION ---
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

if not API_KEY:
    print("⚠️ WARNING: 'TWELVE_DATA_API_KEY' environment variable not detected.")

twwear_symbols = {
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
}

yf_symbols = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X", "USDCHF": "CHF=X",
    "XAUUSD": "GC=F", "SPX": "ES=F", "DAX": "^GDAXI"
}

yf_hourly_targets = ["XAUUSD", "SPX", "DAX"]

os.makedirs("data", exist_ok=True)
all_data_frames = []

# ==========================================
# 1. FETCH FOREX HOURLY (Twelve Data)
# ==========================================
if API_KEY and not API_KEY.startswith("YOUR"):
    for name, ticker in twwear_symbols.items():
        print(f"📥 Fetching Max Hourly History from Twelve Data: {name}")
        url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=5000&apikey={API_KEY}"
        try:
            response = requests.get(url).json()
            if "values" in response:
                h_df = pd.DataFrame(response['values'])
                h_df = h_df.rename(columns={'datetime': 'DateTime', 'open':'Open', 'high':'High', 'low':'Low', 'close':'Close'})
                h_df[['Open', 'High', 'Low', 'Close']] = h_df[['Open', 'High', 'Low', 'Close']].apply(pd.to_numeric)
                h_df['DateTime'] = pd.to_datetime(h_df['DateTime'])
                h_df['Instrument'] = name
                h_df['TimeFrame'] = '1h'
                h_df['Source'] = 'TwelveData'
                all_data_frames.append(h_df)
                print(f"✅ Retrieved {len(h_df)} hourly bars for {name}")
            else:
                print(f"❌ Twelve Data API error for {name}: {response.get('message')}")
        except Exception as e:
            print(f"❌ Connection failed for {name}: {e}")
        
        time.sleep(10)
else:
    print("箱 Skipping Twelve Data (No API Key set).")

# ==========================================
# 2. FETCH INDICES & GOLD HOURLY (yfinance)
# ==========================================
for name in yf_hourly_targets:
    ticker = yf_symbols[name]
    print(f"📥 Fetching Max Hourly History from yfinance: {name}")
    try:
        # Pass group_by="ticker" to keep the sub-columns uniform
        h_df = yf.download(ticker, period="730d", interval="1h", progress=False, group_by="ticker")
        if not h_df.empty:
            if isinstance(h_df.columns, pd.MultiIndex):
                h_df = h_df[ticker] if ticker in h_df.columns.levels[0] else h_df.droplevel(1, axis=1)
            
            h_df = h_df.reset_index()
            # Rename mapping handling case variations cleanly
            h_df = h_df.rename(columns={'Datetime': 'DateTime', 'Date': 'DateTime', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
            
            h_df = h_df.dropna(subset=['Close'])
            h_df['DateTime'] = pd.to_datetime(h_df['DateTime']).dt.tz_localize(None)
            h_df['Instrument'] = name
            h_df['TimeFrame'] = '1h'
            h_df['Source'] = 'yfinance'
            
            h_df = h_df[['DateTime', 'Open', 'High', 'Low', 'Close', 'Instrument', 'TimeFrame', 'Source']]
            all_data_frames.append(h_df)
            print(f"✅ Retrieved {len(h_df)} hourly bars for {name}")
    except Exception as e:
        print(f"❌ Failed fetching yfinance hourly for {name}: {e}")

# ==========================================
# 3. FETCH ALL ASSETS WEEKLY (yfinance)
# ==========================================
for name, ticker in yf_symbols.items():
    print(f"📥 Fetching Max Weekly History from yfinance: {name}")
    try:
        w_df = yf.download(ticker, period="max", interval="1wk", progress=False, group_by="ticker")
        if not w_df.empty:
            if isinstance(w_df.columns, pd.MultiIndex):
                w_df = w_df[ticker] if ticker in w_df.columns.levels[0] else w_df.droplevel(1, axis=1)
            
            w_df = w_df.reset_index()
            w_df = w_df.rename(columns={'Date': 'DateTime', 'Datetime': 'DateTime', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
            
            w_df = w_df.dropna(subset=['Close'])
            w_df['DateTime'] = pd.to_datetime(w_df['DateTime']).dt.tz_localize(None)
            w_df['Instrument'] = name
            w_df['TimeFrame'] = '1wk'
            w_df['Source'] = 'yfinance'
            
            w_df = w_df[['DateTime', 'Open', 'High', 'Low', 'Close', 'Instrument', 'TimeFrame', 'Source']]
            all_data_frames.append(w_df)
            print(f"✅ Retrieved {len(w_df)} weekly bars for {name}")
    except Exception as e:
        print(f"❌ Failed fetching yfinance weekly for {name}: {e}")

# ==========================================
# 4. SAVE COMPILED FILE TO RAW REPO STORAGE
# ==========================================
if all_data_frames:
    master_historical_df = pd.concat(all_data_frames, ignore_index=True)
    master_historical_df = master_historical_df.dropna(subset=['DateTime', 'Open', 'Close'])
    master_historical_df = master_historical_df.sort_values(['Instrument', 'TimeFrame', 'DateTime'])
    
    output_path = os.path.join("data", "raw_hourly_history.csv")
    master_historical_df.to_csv(output_path, index=False)
    print(f"\n🚀 SUCCESS: Database cleanly compiled with {len(master_historical_df)} total mixed rows.")
else:
    print("❌ Failure: No data could be gathered.")
