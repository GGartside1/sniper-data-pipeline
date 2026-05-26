{{ config(materialized='table') }}

SELECT
    execution_week,
    instrument,
    api_provider,
    true_open_timestamp,
    -- Extract the day of the week (1 = Monday, 7 = Sunday)
    EXTRACT(DAYOFWEEK_ISO FROM true_open_timestamp) as open_day_of_week,
    EXTRACT(HOUR FROM true_open_timestamp) as open_hour,
    
    -- VALIDATION FLAG: If the first bar we found is happening on a Tuesday or later (Day 2+), flag it as a data gap!
    CASE 
        WHEN EXTRACT(DAYOFWEEK_ISO FROM true_open_timestamp) NOT IN (7, 1) THEN 'WARNING: Delayed First Bar (Potential Data Gap)'
        ELSE 'VALID'
    END as data_integrity_status

FROM {{ ref('int_true_weekly_opens') }}