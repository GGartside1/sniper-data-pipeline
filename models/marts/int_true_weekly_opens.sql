{{ config(materialized='view') }}

WITH local_bars AS (
    SELECT
        record_timestamp,
        instrument,
        asset_class,
        api_provider,
        open_price,
        close_price,
        
        -- Extract the day of the week (0 = Sunday, 1 = Monday... 5 = Friday, 6 = Saturday)
        DAYOFWEEK(record_timestamp) as day_of_week,
        -- Extract the hour of the day (0 to 23)
        HOUR(record_timestamp) as hour_of_day
    FROM {{ ref('stg_historical_prices') }}
    WHERE timeframe = '1h'
),

-- Isolate the absolute true market opening bars on Sunday night
true_sunday_opens AS (
    SELECT
        *,
        -- Generate a standard clean text identifier for the trading week (YYYY-MM-DD of the actual opening Monday)
        -- If it's Sunday, add 1 day to find the Monday trading date anchor. If it's already Monday, keep it.
        CASE 
            WHEN day_of_week = 0 THEN CAST(DATEADD(day, 1, record_timestamp) AS DATE)
            ELSE CAST(record_timestamp AS DATE)
        END as execution_week_anchor
    FROM local_bars
    -- Filter condition: It must be Sunday evening after 21:00 local time OR Monday morning early
    WHERE (day_of_week = 0 AND hour_of_day >= 21) 
       OR (day_of_week = 1 AND hour_of_day BETWEEN 0 AND 4)
),

ranked_true_opens AS (
    SELECT
        execution_week_anchor,
        instrument,
        asset_class,
        api_provider,
        record_timestamp as true_open_timestamp,
        open_price as true_weekly_open,
        
        -- Row number 1 will now strictly be the first valid bar of the new trading session
        ROW_NUMBER() OVER (
            PARTITION BY instrument, execution_week_anchor 
            ORDER BY record_timestamp ASC
        ) as true_chronology
    FROM true_sunday_opens
)

SELECT
    execution_week_anchor as execution_week,
    instrument,
    asset_class,
    api_provider,
    true_open_timestamp,
    true_weekly_open
FROM ranked_true_opens
WHERE true_chronology = 1