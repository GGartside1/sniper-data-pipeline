{{ config(materialized='table') }}

WITH true_opens AS (
    -- Step 1: Establish anchor definitions cleanly from our intermediate model
    SELECT 
        execution_week,
        instrument,
        asset_class,
        api_provider,
        true_open_timestamp,
        true_weekly_open
    FROM {{ ref('int_true_weekly_opens') }}
),

weekly_metrics_aggregated AS (
    -- Step 2: Grab structural extremes and the true weekly close using a QUALIFY filter to avoid GROUP BY pollution
    SELECT 
        o.execution_week,
        o.instrument,
        -- Global aggregates across the partitioned timeframe window
        MAX(s.high_price) OVER (PARTITION BY o.instrument, o.execution_week) as weekly_max_high,
        MIN(s.low_price) OVER (PARTITION BY o.instrument, o.execution_week) as weekly_max_low,
        
        -- Exact final close price of the week
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
    -- Isolate exactly 1 row per instrument per week containing all historical metrics
    QUALIFY ROW_NUMBER() OVER (PARTITION BY o.instrument, o.execution_week ORDER BY s.record_timestamp DESC) = 1
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
        
        -- Intra-week peak expansion returns (Captures the full absolute structural footprint)
        GREATEST(e.weekly_max_high - o.true_weekly_open, 0) / NULLIF(o.true_weekly_open, 0) as up_expansion_return,
        GREATEST(o.true_weekly_open - e.weekly_max_low, 0) / NULLIF(o.true_weekly_open, 0) as dn_expansion_return
        
    FROM true_opens o
    LEFT JOIN weekly_metrics_aggregated e
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
        true_weekly_close as weekly_close,
        
        up_expansion_return as up_ext,
        dn_expansion_return as dn_ext,

        -- 🛡️ FIXED: 26-week distribution profiles (Strictly 25 preceding rows + 1 preceding row = 26 data points)
        AVG(up_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 25 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_up_mean,
        
        AVG(dn_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 25 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_dn_mean,

        STDDEV(up_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 25 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_up_stddev,
        
        STDDEV(dn_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 25 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_dn_stddev,

        -- Keep an un-shifted stddev metric/filtering global outliers out at the final step
        STDDEV(up_expansion_return) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC
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
    up_ext,
    dn_ext,
    rolling_26wk_up_mean,
    rolling_26wk_dn_mean,
    rolling_26wk_up_stddev,
    rolling_26wk_dn_stddev
FROM calculated_metrics
WHERE raw_global_stddev < 9 OR raw_global_stddev IS NULL