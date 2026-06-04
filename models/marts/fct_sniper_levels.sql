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

-- Step 1: Calculate Realized Asymmetric Multipliers ONLY for completed historical weeks
realized_multipliers AS (
    SELECT 
        *,
        (up_ext - rolling_26wk_up_mean) / NULLIF(rolling_26wk_up_stddev, 0) as realized_up_sd,
        (dn_ext - rolling_26wk_dn_mean) / NULLIF(rolling_26wk_dn_stddev, 0) as realized_dn_sd
    FROM base_metrics
    -- We don't want the live, fluctuating week polluting the historical quantile distributions
    WHERE weekly_close IS NOT NULL 
),

-- Step 2: Compute clean, static Global Empirical Quantiles per instrument
empirical_quantiles AS (
    SELECT 
        instrument,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_50,
        PERCENTILE_CONT(0.60) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_60,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY realized_up_sd ASC) OVER (PARTITION BY instrument) as q_up_90,

        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_50,
        PERCENTILE_CONT(0.60) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_60,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY realized_dn_sd DESC) OVER (PARTITION BY instrument) as q_dn_90
    FROM realized_multipliers
    GROUP BY instrument, realized_up_sd, realized_dn_sd
    QUALIFY ROW_NUMBER() OVER (PARTITION BY instrument ORDER BY instrument) = 1
),

-- Step 3: Map the static profiles cleanly onto ALL weeks (including the active live anchor)
forward_shifted_signals AS (
    SELECT 
        b.record_week,
        b.instrument,
        b.true_weekly_open as current_week_open,
        b.weekly_close,
        
        -- Pull the distributions from the previous completed row anchor
        LAG(b.rolling_26wk_up_mean, 1) OVER (PARTITION BY b.instrument ORDER BY b.record_week ASC) as prior_up_mean,
        LAG(b.rolling_26wk_dn_mean, 1) OVER (PARTITION BY b.instrument ORDER BY b.record_week ASC) as prior_dn_mean,
        LAG(b.rolling_26wk_up_stddev, 1) OVER (PARTITION BY b.instrument ORDER BY b.record_week ASC) as prior_up_stddev,
        LAG(b.rolling_26wk_dn_stddev, 1) OVER (PARTITION BY b.instrument ORDER BY b.record_week ASC) as prior_dn_stddev,
        
        q.q_up_50, q.q_up_60, q.q_up_75, q.q_up_90,
        q.q_dn_50, q.q_dn_60, q.q_dn_75, q.q_dn_90
    FROM base_metrics b
    LEFT JOIN empirical_quantiles q 
        ON b.instrument = q.instrument
),

-- Step 4: Setup dynamic multiplier pip scales and precise decimal round settings
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
        END as pip_unit,
        
        -- 2 Decimals for stock index instruments, 5 Decimals for FX and Spot Gold
        CASE 
            WHEN instrument LIKE '%SPX%' OR instrument LIKE '%DAX%' THEN 2
            ELSE 5
        END as round_scale
    FROM forward_shifted_signals
)

-- Final Step: Generate beautifully rounded final assets with CORRECTED sign directions
SELECT 
    record_week,
    instrument,
    ROUND(current_week_open, round_scale) as current_week_open,
    pip_unit,

    -- Upside remains additive
    ROUND(current_week_open * (1 + prior_up_mean), round_scale) as baseline_up_mean_price,
    
    -- 🛑 FIXED: Downside subtracts the mean return to project lower prices
    ROUND(current_week_open * (1 - prior_dn_mean), round_scale) as baseline_dn_price,

    ROUND((current_week_open * prior_up_stddev) * pip_multiplier, 2) as up_1_sd_in_units,
    ROUND((current_week_open * prior_dn_stddev) * pip_multiplier, 2) as dn_1_sd_in_units,

    -- Rounded Empirical Sniper Upside Execution Levels (Additive)
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_50 * prior_up_stddev))), round_scale) as up_fail_50,
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_60 * prior_up_stddev))), round_scale) as up_fail_60,
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_75 * prior_up_stddev))), round_scale) as up_fail_75,
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_90 * prior_up_stddev))), round_scale) as up_fail_90,

    -- 🛑 FIXED: Empirical Sniper Downside Execution Levels (Subtractive)
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_50 * prior_dn_stddev))), round_scale) as dn_fail_50,
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_60 * prior_dn_stddev))), round_scale) as dn_fail_60,
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_75 * prior_dn_stddev))), round_scale) as dn_fail_75,
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_90 * prior_dn_stddev))), round_scale) as dn_fail_90

FROM unit_multipliers