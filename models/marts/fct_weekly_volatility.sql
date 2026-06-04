{{ config(materialized='table') }}

WITH true_opens AS (
    -- Step 1: Establish our anchor definitions cleanly from our intermediate model
    SELECT 
        execution_week,
        instrument,
        asset_class,
        api_provider,
        true_open_timestamp,
        true_weekly_open
    FROM {{ ref('int_true_weekly_opens') }}
),

weekly_hourly_metrics AS (
    -- Step 2: Extract highs, lows, AND the true closing price from the final hourly bar of the week
    SELECT 
        o.execution_week,
        o.instrument,
        MAX(s.high_price) as weekly_max_high,
        MIN(s.low_price) as weekly_max_low,
        
        -- Grab the absolute last close price of the week
        LAST_VALUE(s.close_price) OVER (
            PARTITION BY o.instrument, o.execution_week 
            ORDER BY s.record_timestamp ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) as true_weekly_close
        
    FROM {{ ref('stg_historical_prices') }} s
    INNER JOIN true_opens o 
        ON s.instrument = o.instrument
        AND s.record_timestamp >= o.true_open_timestamp
        AND s.record_timestamp < DATEADD(day, 7, o.true_open_timestamp)
    WHERE s.timeframe = '1h'
    GROUP BY o.execution_week, o.instrument, s.close_price, s.record_timestamp
),

weekly_extremes_collapsed AS (
    -- Deduplicate grouped metrics down to one clean row per instrument per week anchor
    SELECT
        execution_week,
        instrument,
        MAX(weekly_max_high) as weekly_max_high,
        MIN(weekly_max_low) as weekly_max_low,
        MAX(true_weekly_close) as true_weekly_close
    FROM weekly_hourly_metrics
    GROUP BY execution_week, instrument
),

joined_pipeline AS (
    -- Step 3: Compute expansions based on pure intra-week physics
    SELECT 
        o.execution_week,
        o.instrument,
        o.asset_class,
        o.api_provider,
        o.true_weekly_open,
        e.true_weekly_close,
        
        -- Intra-week peak expansion returns (Captures the full structural footprint)
        (e.weekly_max_high - o.true_weekly_open) / NULLIF(o.true_weekly_open, 0) as up_expansion_return,
        (o.true_weekly_open - e.weekly_max_low) / NULLIF(o.true_weekly_open, 0) as dn_expansion_return
        
    FROM true_opens o
    LEFT JOIN weekly_extremes_collapsed e
        ON o.execution_week = e.execution_week 
       AND o.instrument = e.instrument
),

calculated_metrics AS (
    SELECT 
        execution_week as record_week,
        instrument,
        asset_class,
        api_provider,
        true_weekly_open,
        true_weekly_close as weekly_close, -- 👈 Dynamically derived weekly close replaces the old seed!
        
        up_expansion_return as weekly_expansion_return,
        up_expansion_return as up_ext,
        dn_expansion_return as dn_ext,

        -- 26-week distribution profiles
        AVG(up_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_up_mean,
        
        AVG(dn_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_dn_mean,

        STDDEV(up_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_up_stddev,
        
        STDDEV(dn_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_dn_stddev,

        STDDEV(up_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as raw_global_stddev

    FROM joined_pipeline
)

SELECT 
    record_week,
    instrument,
    asset_class,
    api_provider,
    true_weekly_open,
    weekly_close,
    weekly_expansion_return,
    up_ext,
    dn_ext,
    rolling_26wk_up_mean,
    rolling_26wk_dn_mean,
    rolling_26wk_up_stddev,
    rolling_26wk_dn_stddev
FROM calculated_metrics
WHERE raw_global_stddev < 9 OR raw_global_stddev IS NULL