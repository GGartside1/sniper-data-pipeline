{{ config(materialized='view') }}

WITH raw_source AS (
    SELECT * FROM {{ source('sniper_raw', 'HISTORICAL_LEADERBOARD') }}
),

categorized_data AS (
    SELECT
        -- 1. Standardize Timestamps & Dates with explicit Timezone Mapping
        CASE UPPER(TRIM(SOURCE))
            WHEN 'TWELVEDATA' THEN CONVERT_TIMEZONE('Australia/Sydney', 'Europe/Stockholm', TRY_TO_TIMESTAMP(DATETIME))
            WHEN 'YFINANCE'   THEN CONVERT_TIMEZONE('UTC', 'Europe/Stockholm', TRY_TO_TIMESTAMP(DATETIME))
            ELSE TRY_TO_TIMESTAMP(DATETIME)
        END as record_timestamp,

        -- Derive the clean local date directly from our normalized timestamp
        CAST(record_timestamp AS DATE) as record_date,
        
        -- 2. Clean up Text Strings
        UPPER(TRIM(INSTRUMENT)) as instrument,
        LOWER(TRIM(TIMEFRAME)) as timeframe,
        UPPER(TRIM(SOURCE)) as api_provider,
        
        -- 3. Explicit Asset Class Tagging
        CASE 
            WHEN UPPER(TRIM(INSTRUMENT)) IN ('DAX', 'SPX') THEN 'index'
            WHEN UPPER(TRIM(INSTRUMENT)) IN ('XAUUSD') THEN 'commodity'
            ELSE 'forex'
        END as asset_class,

        -- 4. Standardize Numeric Pricing Fields
        CAST(OPEN AS FLOAT) as open_price,
        CAST(HIGH AS FLOAT) as high_price,
        CAST(LOW AS FLOAT) as low_price,
        CAST(CLOSE AS FLOAT) as close_price,

        -- 5. Timezone-Aligned Ingestion Metadata (Forcing UTC runner time to Stockholm)
        CONVERT_TIMEZONE('UTC', 'Europe/Stockholm', CURRENT_TIMESTAMP()) as dbt_processed_at

    FROM raw_source
    WHERE INSTRUMENT IS NOT NULL 
      AND CLOSE IS NOT NULL
)

SELECT * FROM categorized_data