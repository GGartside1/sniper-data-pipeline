{{ config(materialized='view') }}

WITH hourly_bars AS (
    SELECT
        record_timestamp,
        -- DATE_TRUNC forces any Sunday night or Monday bar into the exact same Monday date anchor
        DATE_TRUNC('week', record_timestamp) as execution_week,
        instrument,
        asset_class,
        api_provider,
        open_price as hourly_open,
        close_price as hourly_close
    FROM {{ ref('stg_historical_prices') }}
    WHERE timeframe = '1h'
),

ranked_hourly_bars AS (
    SELECT
        *,
        -- Row number 1 will ALWAYS be the first bar that showed up that week, regardless of whether it's Sunday 23:00 or Monday 01:00
        ROW_NUMBER() OVER (
            PARTITION BY instrument, execution_week 
            ORDER BY record_timestamp ASC
        ) as bar_chronology
    FROM hourly_bars
)

SELECT
    execution_week,
    instrument,
    asset_class,
    api_provider,
    record_timestamp as true_open_timestamp,
    hourly_open as true_weekly_open
FROM ranked_hourly_bars
-- Quarantine step: Pull only the absolute first bar of the week
WHERE bar_chronology = 1