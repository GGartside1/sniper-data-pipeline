import os
import pandas as pd
import numpy as np
import requests
import time
import yfinance as yf

# --- CONFIGURATION ---
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

twelve_symbols = {
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
    for name, ticker in twelve_symbols.items():
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
    print("⏭️ Skipping Twelve Data (No API Key set).")

# ==========================================
# 2. FETCH INDICES & GOLD HOURLY (yfinance via Notebook Stack method)
# ==========================================
print("📥 Fetching Bulk Hourly History from yfinance...")
try:
    hourly_tickers = [yf_symbols[name] for name in yf_hourly_targets]
    # Download everything at once matching your notebook design patterns
    raw_h_df = yf.download(hourly_tickers, period="730d", interval="1h", progress=False)
    
    if not raw_h_df.empty:
        # Replicate your exact notebook stacking fix to flatten the MultiIndex layer
        h_df = raw_h_df.stack(level=1, future_stack=True).reset_index()
        
        # Reverse map the symbols back to your asset names
        inv_yf_symbols = {v: k for k, v in yf_symbols.items()}
        h_df['Instrument'] = h_df['Ticker'].map(inv_yf_symbols)
        
        # Clean column remapping string adjustments
        h_df = h_df.rename(columns={'Datetime': 'DateTime', 'Date': 'DateTime'})
        h_df['DateTime'] = pd.to_datetime(h_df['DateTime']).dt.tz_localize(None)
        h_df['TimeFrame'] = '1h'
        h_df['Source'] = 'yfinance'
        
        # Isolate target constraints
        h_df = h_df[['DateTime', 'Open', 'High', 'Low', 'Close', 'Instrument', 'TimeFrame', 'Source']]
        h_df = h_df.dropna(subset=['Close'])
        
        all_data_frames.append(h_df)
        print(f"✅ Bulk Hourly Retrieval Complete. Processed bars.")
except Exception as e:
    print(f"❌ Failed bulk yfinance hourly processing calculation layout: {e}")

# ==========================================
# 3. FETCH ALL ASSETS WEEKLY (yfinance via Notebook Stack method)
# ==========================================
print("📥 Fetching Bulk Weekly History from yfinance...")
try:
    weekly_tickers = list(yf_symbols.values())
    raw_w_df = yf.download(weekly_tickers, period="max", interval="1wk", progress=False)
    
    if not raw_w_df.empty:
        w_df = raw_w_df.stack(level=1, future_stack=True).reset_index()
        
        inv_yf_symbols = {v: k for k, v in yf_symbols.items()}
        w_df['Instrument'] = w_df['Ticker'].map(inv_yf_symbols)
        
        w_df = w_df.rename(columns={'Date': 'DateTime', 'Datetime': 'DateTime'})
        w_df['DateTime'] = pd.to_datetime(w_df['DateTime']).dt.tz_localize(None)
        w_df['TimeFrame'] = '1wk'
        w_df['Source'] = 'yfinance'
        
        w_df = w_df[['DateTime', 'Open', 'High', 'Low', 'Close', 'Instrument', 'TimeFrame', 'Source']]
        w_df = w_df.dropna(subset=['Close'])
        
        all_data_frames.append(w_df)
        print(f"✅ Bulk Weekly Retrieval Complete. Processed bars.")
except Exception as e:
    print(f"❌ Failed bulk yfinance weekly processing calculation layout: {e}")

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
