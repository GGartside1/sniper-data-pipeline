import os
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import traceback

# ==========================================
# CONFIGURATION
# ==========================================
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

twelve_symbols = {
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
}

yf_symbols = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X", "USDCHF": "CHF=X",
    "XAUUSD": "GC=F", "SPX": "ES=F", "DAX": "^GDAXI",
}

yf_hourly_targets = ["XAUUSD", "SPX", "DAX"]
os.makedirs("data", exist_ok=True)
all_data_frames = []

# ==========================================
# 1. FETCH FOREX HOURLY (TWELVE DATA)
# ==========================================
if API_KEY and not API_KEY.startswith("YOUR"):
    for name, ticker in twelve_symbols.items():
        print(f"📥 Fetching Twelve Data hourly history: {name}")
        url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=5000&apikey={API_KEY}"
        try:
            response = requests.get(url, timeout=30).json()
            if "values" in response:
                h_df = pd.DataFrame(response["values"])
                h_df = h_df.rename(columns={"datetime": "DateTime", "open": "Open", "high": "High", "low": "Low", "close": "Close"})
                h_df[["Open", "High", "Low", "Close"]] = h_df[["Open", "High", "Low", "Close"]].apply(pd.to_numeric, errors="coerce")
                h_df["DateTime"] = pd.to_datetime(h_df["DateTime"])
                h_df["Instrument"] = name
                h_df["TimeFrame"] = "1h"
                h_df["Source"] = "TwelveData"
                h_df = h_df[["DateTime", "Open", "High", "Low", "Close", "Instrument", "TimeFrame", "Source"]].dropna(subset=["Close"])
                all_data_frames.append(h_df)
                print(f"✅ Retrieved {len(h_df)} hourly rows for {name}")
        except Exception as e:
            print(f"❌ Failed Twelve Data fetch for {name}: {e}")
        time.sleep(10)
else:
    print("⏭️ Skipping Twelve Data (No API key found).")

# ==========================================
# 2. FETCH HOURLY YFINANCE DATA
# ==========================================
print("\n📥 Fetching hourly yfinance history...")
for asset_name in yf_hourly_targets:
    ticker = yf_symbols[asset_name]
    print(f"📥 Fetching yfinance hourly: {asset_name} ({ticker})")
    for attempt in range(3):
        try:
            # Set to 730d max hard limit allowed for 1h bar extraction
            df = yf.download(ticker, period="730d", interval="1h", auto_adjust=False, progress=False, threads=False)
            if df.empty:
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Reset index BEFORE inspecting names to make Date/Datetime an explicit column
            df = df.reset_index()
            df.columns = [str(col) for col in df.columns]
            
            # Use case-insensitive checking for structural safety
            df = df.rename(columns={"Datetime": "DateTime", "Date": "DateTime", "open": "Open", "high": "High", "low": "Low", "close": "Close"})
            df["DateTime"] = pd.to_datetime(df["DateTime"]).dt.tz_localize(None)
            df["Instrument"] = asset_name
            df["TimeFrame"] = "1h"
            df["Source"] = "yfinance"
            
            df = df[["DateTime", "Open", "High", "Low", "Close", "Instrument", "TimeFrame", "Source"]].dropna(subset=["Close"])
            all_data_frames.append(df)
            print(f"✅ Retrieved {len(df)} hourly rows for {ticker}")
            break
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed for {ticker}: {e}")
            time.sleep(5)
    time.sleep(10)

# ==========================================
# 3. FETCH WEEKLY YFINANCE DATA
# ==========================================
print("\n📥 Fetching weekly yfinance history...")
for asset_name, ticker in yf_symbols.items():
    print(f"📥 Fetching weekly: {asset_name} ({ticker})")
    for attempt in range(3):
        try:
            df = yf.download(ticker, period="max", interval="1wk", auto_adjust=False, progress=False, threads=False)
            if df.empty:
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Reset index here to bring 'Date' into the columns array safely
            df = df.reset_index()
            df.columns = [str(col) for col in df.columns]
            
            df = df.rename(columns={"Datetime": "DateTime", "Date": "DateTime", "open": "Open", "high": "High", "low": "Low", "close": "Close"})
            df["DateTime"] = pd.to_datetime(df["DateTime"]).dt.tz_localize(None)
            df["Instrument"] = asset_name
            df["TimeFrame"] = "1wk"
            df["Source"] = "yfinance"
            
            df = df[["DateTime", "Open", "High", "Low", "Close", "Instrument", "TimeFrame", "Source"]].dropna(subset=["Close"])
            all_data_frames.append(df)
            print(f"✅ Retrieved {len(df)} weekly rows for {ticker}")
            break
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed for {ticker}: {e}")
            time.sleep(5)
    time.sleep(10)

# ==========================================
# 4. SAVE COMPILED FILE
# ==========================================
if all_data_frames:
    master_historical_df = pd.concat(all_data_frames, ignore_index=True)
    master_historical_df = master_historical_df.dropna(subset=["DateTime", "Open", "Close"])
    master_historical_df = master_historical_df.sort_values(["Instrument", "TimeFrame", "DateTime"])
    master_historical_df.to_csv(os.path.join("data", "raw_hourly_history.csv"), index=False)
    print(f"\n🚀 SUCCESS: Database cleanly compiled with {len(master_historical_df)} total mixed rows.")
