# ==========================================
# 2. FETCH HOURLY YFINANCE DATA
# ==========================================
print("\n📥 Fetching hourly yfinance history...")

import traceback

inv_yf_symbols = {v: k for k, v in yf_symbols.items()}

hourly_frames = []

for asset_name in yf_hourly_targets:

    ticker = yf_symbols[asset_name]

    print(f"\n📥 Fetching yfinance hourly: {asset_name} ({ticker})")

    success = False

    # Retry logic
    for attempt in range(3):

        try:

            df = yf.download(
                ticker,
                period="60d",          # Yahoo limit for intraday data
                interval="1h",
                auto_adjust=False,
                progress=False,
                threads=False,
                prepost=False,
            )

            print(f"\n===== DEBUG FOR {ticker} =====")
            print(type(df))
            print(df.shape)

            try:
                print(df.head())
            except Exception as e:
                print(f"HEAD FAILED: {e}")

            try:
                print(df.columns)
            except Exception as e:
                print(f"COLUMNS FAILED: {e}")

            print("=================================\n")

            # FIX MULTIINDEX COLUMNS
            if isinstance(df.columns, pd.MultiIndex):
                print(f"⚠️ Flattening MultiIndex columns for {ticker}")
                df.columns = df.columns.get_level_values(0)

            print(f"Flattened columns: {df.columns.tolist()}")

            if df.empty:
                print(f"❌ Empty dataframe for {ticker}")
                time.sleep(5)
                continue

            # Reset index
            df = df.reset_index()

            # Normalize datetime column
            if "Datetime" in df.columns:
                df = df.rename(columns={"Datetime": "DateTime"})
            elif "Date" in df.columns:
                df = df.rename(columns={"Date": "DateTime"})

            # Remove timezone
            df["DateTime"] = (
                pd.to_datetime(df["DateTime"])
                .dt.tz_localize(None)
            )

            # Metadata
            df["Instrument"] = asset_name
            df["TimeFrame"] = "1h"
            df["Source"] = "yfinance"

            # Keep required columns
            df = df[
                [
                    "DateTime",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Instrument",
                    "TimeFrame",
                    "Source",
                ]
            ]

            # Remove NaNs
            df = df.dropna(subset=["Close"])

            hourly_frames.append(df)

            print(f"✅ Retrieved {len(df)} hourly rows for {ticker}")

            success = True
            break

        except Exception as e:

            print(f"\n❌ Attempt {attempt + 1} failed for {ticker}")
            traceback.print_exc()

            time.sleep(5)

    if not success:
        print(f"❌ Failed all retries for {ticker}")

    # Avoid Yahoo throttling
    time.sleep(10)

if hourly_frames:

    hourly_df = pd.concat(hourly_frames, ignore_index=True)

    all_data_frames.append(hourly_df)

    print(
        f"\n✅ Combined yfinance hourly rows: {len(hourly_df)}"
    )

else:
    print("❌ No hourly yfinance data retrieved.")


# ==========================================
# 3. FETCH WEEKLY YFINANCE DATA
# ==========================================
print("\n📥 Fetching weekly yfinance history...")

weekly_frames = []

for asset_name, ticker in yf_symbols.items():

    print(f"\n📥 Fetching weekly: {asset_name} ({ticker})")

    success = False

    for attempt in range(3):

        try:

            df = yf.download(
                ticker,
                period="max",
                interval="1wk",
                auto_adjust=False,
                progress=False,
                threads=False,
                prepost=False,
            )

            print(f"\n===== DEBUG FOR {ticker} =====")
            print(type(df))
            print(df.shape)

            try:
                print(df.head())
            except Exception as e:
                print(f"HEAD FAILED: {e}")

            try:
                print(df.columns)
            except Exception as e:
                print(f"COLUMNS FAILED: {e}")

            print("=================================\n")

            # FIX MULTIINDEX COLUMNS
            if isinstance(df.columns, pd.MultiIndex):
                print(f"⚠️ Flattening MultiIndex columns for {ticker}")
                df.columns = df.columns.get_level_values(0)

            print(f"Flattened columns: {df.columns.tolist()}")

            if df.empty:
                print(f"❌ Empty weekly dataframe for {ticker}")
                time.sleep(5)
                continue

            # Reset index
            df = df.reset_index()

            # Normalize datetime column
            if "Datetime" in df.columns:
                df = df.rename(columns={"Datetime": "DateTime"})
            elif "Date" in df.columns:
                df = df.rename(columns={"Date": "DateTime"})

            # Remove timezone
            df["DateTime"] = (
                pd.to_datetime(df["DateTime"])
                .dt.tz_localize(None)
            )

            # Metadata
            df["Instrument"] = asset_name
            df["TimeFrame"] = "1wk"
            df["Source"] = "yfinance"

            # Keep required columns
            df = df[
                [
                    "DateTime",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Instrument",
                    "TimeFrame",
                    "Source",
                ]
            ]

            # Remove NaNs
            df = df.dropna(subset=["Close"])

            weekly_frames.append(df)

            print(f"✅ Retrieved {len(df)} weekly rows for {ticker}")

            success = True
            break

        except Exception as e:

            print(f"\n❌ Attempt {attempt + 1} failed for {ticker}")
            traceback.print_exc()

            time.sleep(5)

    if not success:
        print(f"❌ Failed all retries for {ticker}")

    # Avoid Yahoo throttling
    time.sleep(10)

if weekly_frames:

    weekly_df = pd.concat(weekly_frames, ignore_index=True)

    all_data_frames.append(weekly_df)

    print(
        f"\n✅ Combined yfinance weekly rows: {len(weekly_df)}"
    )

else:
    print("❌ No weekly yfinance data retrieved.")
