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
    -- Don't want the live, fluctuating week polluting the historical quantile distributions
    WHERE weekly_close IS NOT NULL 
),

-- Step 2a: Contextualize each week with its true 26-week trailing history
rolling_window_context AS (
    SELECT 
        curr.INSTRUMENT,
        curr.RECORD_WEEK,
        -- Pull the historical records that fall within the 26-week training lookback
        hist.REALIZED_UP_SD AS hist_up_sd,
        hist.REALIZED_DN_SD AS hist_dn_sd
    FROM realized_multipliers curr
    INNER JOIN realized_multipliers hist
        ON curr.INSTRUMENT = hist.INSTRUMENT
        -- Lookback window: Trailing 26 weeks excluding the live/current week
        AND hist.RECORD_WEEK >= DATEADD('week', -26, curr.RECORD_WEEK)
        AND hist.RECORD_WEEK < curr.RECORD_WEEK
),

-- Step 2b: Compute rolling empirical quantiles based strictly on the 26-week pool
empirical_quantiles AS (
    SELECT 
        INSTRUMENT,
        RECORD_WEEK,
        
        -- Clean 26-week lookback upside percentiles
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY hist_up_sd ASC) AS q_up_50,
        PERCENTILE_CONT(0.60) WITHIN GROUP (ORDER BY hist_up_sd ASC) AS q_up_60,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY hist_up_sd ASC) AS q_up_75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY hist_up_sd ASC) AS q_up_90,

        -- Clean 26-week lookback downside percentiles
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY hist_dn_sd ASC) AS q_dn_50,
        PERCENTILE_CONT(0.60) WITHIN GROUP (ORDER BY hist_dn_sd ASC) AS q_dn_60,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY hist_dn_sd ASC) AS q_dn_75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY hist_dn_sd ASC) AS q_dn_90
    FROM rolling_window_context
    GROUP BY INSTRUMENT, RECORD_WEEK
),

-- Step 3: Map the static profiles cleanly onto ALL weeks (including the active live anchor)
forward_shifted_signals AS (
    SELECT 
        b.record_week,
        b.instrument,
        b.true_weekly_open as current_week_open,
        b.weekly_close,
        
        -- 🛡️ FIXED: Removed redundant LAG() calls. The base metrics are already pre-shifted.
        b.rolling_26wk_up_mean as prior_up_mean,
        b.rolling_26wk_dn_mean as prior_dn_mean,
        b.rolling_26wk_up_stddev as prior_up_stddev,
        b.rolling_26wk_dn_stddev as prior_dn_dev,
        
        q.q_up_50, q.q_up_60, q.q_up_75, q.q_up_90,
        q.q_dn_50, q.q_dn_60, q.q_dn_75, q.q_dn_90
    FROM base_metrics b
    -- 🛡️ FIXED: Added record_week to join condition to prevent massive Cartesian products
    LEFT JOIN empirical_quantiles q 
        ON b.instrument = q.instrument
        AND b.record_week = q.record_week
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

-- Final Step: Generate rounded final assets with CORRECTED sign directions
SELECT 
    record_week,
    instrument,
    ROUND(current_week_open, round_scale) as current_week_open,
    pip_unit,

    -- =========================================================================
    -- BASELINE EXPECTED VOLATILITY (0 Standard Deviation / Absolute Mean)
    -- =========================================================================
    ROUND(current_week_open * (1 + prior_up_mean), round_scale) as baseline_up_mean_price,
    ROUND(current_week_open * (1 - prior_dn_mean), round_scale) as baseline_dn_price,

    ROUND((current_week_open * prior_up_stddev) * pip_multiplier, 2) as up_1_sd_in_units,
    ROUND((current_week_open * prior_dn_dev) * pip_multiplier, 2) as dn_1_sd_in_units,

    -- =========================================================================
    -- UPSIDE SNIPER EXECUTION LEVELS (Additive)
    -- Formula: Open * (1 + Absolute Distance)
    -- =========================================================================
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_50 * prior_up_stddev))), round_scale) as up_fail_50,
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_60 * prior_up_stddev))), round_scale) as up_fail_60,
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_75 * prior_up_stddev))), round_scale) as up_fail_75,
    ROUND(current_week_open * (1 + (prior_up_mean + (q_up_90 * prior_up_stddev))), round_scale) as up_fail_90,

    -- =========================================================================
    -- 🛡️ FIXED: DOWNSIDE SNIPER EXECUTION LEVELS (Subtractive Absolute Packages)
    -- Formula: Open * (1 - (prior_dn_mean + (q_dn_XX * prior_dn_dev)))
    -- =========================================================================
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_50 * prior_dn_dev))), round_scale) as dn_fail_50,
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_60 * prior_dn_dev))), round_scale) as dn_fail_60,
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_75 * prior_dn_dev))), round_scale) as dn_fail_75,
    ROUND(current_week_open * (1 - (prior_dn_mean + (q_dn_90 * prior_dn_dev))), round_scale) as dn_fail_90

FROM unit_multipliers