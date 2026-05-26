{{ config(materialized='table') }}

WITH base_metrics AS (
    SELECT 
        record_week,
        instrument,
        true_weekly_open,
        weekly_close,
        up_ext,
        dn_ext,
        rolling_26wk_up_mean,
        rolling_26wk_dn_mean,
        rolling_26wk_up_stddev,
        rolling_26wk_dn_stddev
    FROM {{ ref('fct_weekly_volatility') }}
),

-- Step 1: Calculate Realized Asymmetric Multipliers
realized_multipliers AS (
    SELECT 
        *,
        (up_ext - rolling_26wk_up_mean) / NULLIF(rolling_26wk_up_stddev, 0) as realized_up_sd,
        (dn_ext - rolling_26wk_dn_mean) / NULLIF(rolling_26wk_dn_stddev, 0) as realized_dn_sd
    FROM base_metrics
),

-- Step 2: Compute Global Empirical Quantiles per instrument
empirical_quantiles AS (
    SELECT 
        *,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_50,
        PERCENTILE_CONT(0.60) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_60,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_90,

        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_50,
        PERCENTILE_CONT(0.60) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_60,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_90
    FROM realized_multipliers
),

-- Step 3: Shift the historical profiles forward to map onto the active current week
forward_shifted_signals AS (
    SELECT 
        record_week,
        instrument,
        true_weekly_open as current_week_open,
        weekly_close,
        
        LAG(rolling_26wk_up_mean, 1) OVER (PARTITION BY instrument ORDER BY record_week ASC) as prior_up_mean,
        LAG(rolling_26wk_dn_mean, 1) OVER (PARTITION BY instrument ORDER BY record_week ASC) as prior_dn_mean,
        LAG(rolling_26wk_up_stddev, 1) OVER (PARTITION BY instrument ORDER BY record_week ASC) as prior_up_stddev,
        LAG(rolling_26wk_dn_stddev, 1) OVER (PARTITION BY instrument ORDER BY record_week ASC) as prior_dn_stddev,
        
        q_up_50, q_up_60, q_up_75, q_up_90,
        q_dn_50, q_dn_60, q_dn_75, q_dn_90
    FROM empirical_quantiles
),

-- Step 4: Inject your exact dynamic Python asset multiplier logic
unit_multipliers AS (
    SELECT 
        *,
        CASE 
            WHEN instrument LIKE '%SPX%' OR instrument LIKE '%DAX%' OR instrument LIKE '%XAUUSD%' THEN 1
            WHEN instrument LIKE '%JPY%' THEN 100
            ELSE 10000 
        END as pip_multiplier,
        
        CASE 
            WHEN instrument LIKE '%SPX%' OR instrument LIKE '%DAX%' OR instrument LIKE '%XAUUSD%' THEN 'pts'
            ELSE 'pips' 
        END as pip_unit
    FROM forward_shifted_signals
)

-- Final Step: Output price configurations, absolute mean targets, and pip buffers
SELECT 
    record_week,
    instrument,
    current_week_open,
    pip_unit,

    -- Volatility Means converted directly to target execution prices
    current_week_open * (1 + prior_up_mean) as baseline_up_mean_price,
    current_week_open * (1 + prior_dn_mean) as baseline_dn_price,

    -- 1 Standard Deviation value expressed cleanly in Pips or Points
    (current_week_open * prior_up_stddev) * pip_multiplier as up_1_sd_in_units,
    (current_week_open * prior_dn_stddev) * pip_multiplier as dn_1_sd_in_units,

    -- Empirical Sniper Execution Levels
    current_week_open * (1 + (prior_up_mean + (q_up_50 * prior_up_stddev))) as up_fail_50,
    current_week_open * (1 + (prior_up_mean + (q_up_60 * prior_up_stddev))) as up_fail_60,
    current_week_open * (1 + (prior_up_mean + (q_up_75 * prior_up_stddev))) as up_fail_75,
    current_week_open * (1 + (prior_up_mean + (q_up_90 * prior_up_stddev))) as up_fail_90,

    current_week_open * (1 + (prior_dn_mean + (q_dn_50 * prior_dn_stddev))) as dn_fail_50,
    current_week_open * (1 + (prior_dn_mean + (q_dn_60 * prior_dn_stddev))) as dn_fail_60,
    current_week_open * (1 + (prior_dn_mean + (q_dn_75 * prior_dn_stddev))) as dn_fail_75,
    current_week_open * (1 + (prior_dn_mean + (q_dn_90 * prior_dn_stddev))) as dn_fail_90

FROM unit_multipliers