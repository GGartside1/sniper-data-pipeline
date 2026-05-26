{{ config(materialized='view') }}

WITH raw_source AS (
    SELECT * FROM {{ source('sniper_raw', 'HISTORICAL_LEADERBOARD') }}
),

categorized_data AS (
    SELECT
        -- 1. Standardize Timestamps & Dates
        TRY_TO_DATE(DATETIME) as record_date,
        TRY_TO_TIMESTAMP(DATETIME) as record_timestamp,
        
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

        -- 5. Automatic Ingestion Metadata
        CURRENT_TIMESTAMP() as dbt_processed_at

    FROM raw_source
    WHERE INSTRUMENT IS NOT NULL 
      AND CLOSE IS NOT NULL
)

SELECT * FROM categorized_data