# ==========================================
# 1. FETCH HOURLY FOREX DELTA (Twelve Data)
# ==========================================
for name, ticker in twelve_symbols.items():
    # FIX: Increase outputsize to 24 to cover any GitHub Actions scheduling delays
    url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=24&apikey={API_KEY}"
    try:
        response = requests.get(url).json()
        if "values" in response and len(response['values']) > 0:
            # FIX: Loop through ALL returned bars instead of just response['values'][0]
            for latest_bar in response['values']:
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
            print(f"✅ Fetched fresh TwelveData history buffer for {name}")
        else:
            print(f"⚠️ No active bars returned from Twelve Data for {name}")
    except Exception as e:
        print(f"❌ Failed to fetch hourly delta from Twelve Data for {name}: {e}")

# ==========================================
# 2. FETCH HOURLY INDICES & GOLD DELTA (yfinance)
# ==========================================
for name, ticker in yf_symbols.items():
    try:
        h_df = yf.download(ticker, period="7d", interval="1h", progress=False, group_by="ticker")
        
        if not h_df.empty:
            if isinstance(h_df.columns, pd.MultiIndex):
                if ticker in h_df.columns.levels[0]:
                    h_df = h_df[ticker]
                else:
                    h_df.columns = h_df.columns.get_level_values(0)

            h_df = h_df.dropna(subset=['Close'])
            if h_df.empty:
                continue

            # FIX: Loop through all rows in the day's dataframe instead of just index[-1]
            for timestamp, latest_bar in h_df.iterrows():
                row = {
                    'DateTime': pd.to_datetime(timestamp).tz_localize(None),
                    'Open': float(latest_bar['Open']),
                    'High': float(latest_bar['High']),
                    'Low': float(latest_bar['Low']),
                    'Close': float(latest_bar['Close']),
                    'Instrument': name,
                    'TimeFrame': '1h',
                    'Source': 'yfinance'
                }
                new_rows.append(row)
            print(f"✅ Fetched fresh yfinance history buffer for {name}")
        else:
            print(f"⚠️ No data returned from yfinance for {name}")
    except Exception as e:
        print(f"❌ Failed to fetch hourly delta from yfinance for {name}: {e}")
