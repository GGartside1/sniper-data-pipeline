{{ config(materialized='table') }}

WITH weekly_closes AS (
    SELECT 
        DATE_TRUNC('week', record_date) as execution_week,
        instrument,
        close_price as weekly_close
    FROM {{ ref('stg_historical_prices') }}
    WHERE timeframe = '1wk'
),

joined_pipeline AS (
    SELECT 
        c.execution_week,
        c.instrument,
        o.asset_class,
        o.api_provider,
        o.true_weekly_open,
        c.weekly_close,
        
        (c.weekly_close - o.true_weekly_open) / NULLIF(o.true_weekly_open, 0) as weekly_expansion_return
    FROM weekly_closes c
    INNER JOIN {{ ref('int_true_weekly_opens') }} o 
        ON c.execution_week = o.execution_week 
       AND c.instrument = o.instrument
),

calculated_metrics AS (
    SELECT 
        execution_week as record_week,
        instrument,
        asset_class,
        api_provider,
        true_weekly_open,
        weekly_close,
        weekly_expansion_return,
        
        CASE WHEN weekly_expansion_return >= 0 THEN weekly_expansion_return ELSE NULL END as up_ext,
        CASE WHEN weekly_expansion_return < 0  THEN weekly_expansion_return ELSE NULL END as dn_ext,

        AVG(CASE WHEN weekly_expansion_return >= 0 THEN weekly_expansion_return ELSE NULL END) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_up_mean,
        
        AVG(CASE WHEN weekly_expansion_return < 0 THEN weekly_expansion_return ELSE NULL END) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_dn_mean,

        STDDEV(CASE WHEN weekly_expansion_return >= 0 THEN weekly_expansion_return ELSE NULL END) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_up_stddev,
        
        STDDEV(CASE WHEN weekly_expansion_return < 0 THEN weekly_expansion_return ELSE NULL END) OVER (
            PARTITION BY instrument ORDER BY execution_week ASC ROWS BETWEEN 26 PRECEDING AND 1 PRECEDING
        ) as rolling_26wk_dn_stddev,

        STDDEV(weekly_expansion_return) OVER (
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