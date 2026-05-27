import os
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf

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
# 1. FETCH FOREX HOURLY (Twelve Data)
# ==========================================
if API_KEY and not API_KEY.startswith("YOUR"):
    for name, ticker in twelve_symbols.items():
        print(f"📥 Fetching Twelve Data hourly history: {name}")
        url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=5000&apikey={API_KEY}"
        try:
            response = requests.get(url, timeout=10).json()
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
                print(f"✅ Appended {len(h_df)} Twelve Data rows for {name}")
        except Exception as e:
            print(f"❌ Failed Twelve Data fetch for {name}: {e}")
        time.sleep(10)
else:
    print("⏭️ Skipping Twelve Data (No API key found).")

# ==========================================
# 2. FETCH HOURLY INDICES & GOLD (yfinance)
# ==========================================
print("\n📥 Fetching hourly yfinance history...")
for asset_name in yf_hourly_targets:
    ticker = yf_symbols[asset_name]
    print(f"📥 Fetching yfinance hourly: {asset_name} ({ticker})")
    try:
        df = yf.download(ticker, period="730d", interval="1h", auto_adjust=False, progress=False, threads=False)
        if not df.empty:
            # Flatten MultiIndex safely if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = df.reset_index()
            
            # Clean tuple strings or odd formatting back to clean string headers
            df.columns = [str(col).replace("('", "").replace("', '')", "").split("',")[0].strip() for col in df.columns]
            
            # Case-insensitive normalization mapping
            df = df.rename(columns={"Datetime": "DateTime", "Date": "DateTime", "open": "Open", "high": "High", "low": "Low", "close": "Close"})
            
            df["DateTime"] = pd.to_datetime(df["DateTime"]).dt.tz_localize(None)
            df["Instrument"] = asset_name
            df["TimeFrame"] = "1h"
            df["Source"] = "yfinance"
            
            df = df[["DateTime", "Open", "High", "Low", "Close", "Instrument", "TimeFrame", "Source"]].dropna(subset=["Close"])
            all_data_frames.append(df)
            print(f"✅ Appended {len(df)} hourly rows for {asset_name}")
    except Exception as e:
        print(f"❌ Failed fetching hourly yfinance for {asset_name}: {e}")
    time.sleep(5)

# ==========================================
# 3. FETCH ALL ASSETS WEEKLY (yfinance)
# ==========================================
print("\n📥 Fetching weekly yfinance history...")
for asset_name, ticker in yf_symbols.items():
    print(f"📥 Fetching yfinance weekly: {asset_name} ({ticker})")
    try:
        df = yf.download(ticker, period="5y", interval="1wk", auto_adjust=False, progress=False, threads=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = df.reset_index()
            
            # Clean headers of tuple wrappers
            df.columns = [str(col).replace("('", "").replace("', '')", "").split("',")[0].strip() for col in df.columns]
            
            df = df.rename(columns={"Date": "DateTime", "Datetime": "DateTime", "open": "Open", "high": "High", "low": "Low", "close": "Close"})
            df["DateTime"] = pd.to_datetime(df["DateTime"]).dt.tz_localize(None)
            df["Instrument"] = asset_name
            df["TimeFrame"] = "1wk"
            df["Source"] = "yfinance"
            
            df = df[["DateTime", "Open", "High", "Low", "Close", "Instrument", "TimeFrame", "Source"]].dropna(subset=["Close"])
            all_data_frames.append(df)
            print(f"✅ Appended {len(df)} weekly rows for {asset_name}")
    except Exception as e:
        print(f"❌ Failed fetching weekly yfinance for {asset_name}: {e}")
    time.sleep(5)

# ==========================================
# 4. CONCATENATE & SAVE
# ==========================================
if all_data_frames:
    master_historical_df = pd.concat(all_data_frames, ignore_index=True)
    master_historical_df = master_historical_df.dropna(subset=["DateTime", "Open", "Close"])
    master_historical_df = master_historical_df.sort_values(["Instrument", "TimeFrame", "DateTime"])
    
    output_path = os.path.join("data", "raw_hourly_history.csv")
    master_historical_df.to_csv(output_path, index=False)
    print(f"\n🚀 PIPELINE SUCCESS: Raw storage compiled with {len(master_historical_df)} uniform asset rows.")
else:
    print("❌ Critical Failure: Zero records were compiled.")
