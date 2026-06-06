-- ====================================================================
-- 1. THE SYNC: Force Snowflake to pull the absolute latest commits from GitHub
-- ====================================================================
ALTER GIT REPOSITORY SNIPER_DB.RAW.SNIPER_REPO FETCH;

-- ====================================================================
-- 2. THE INCREMENTAL UPSERT: Merge only new/updated entries
-- ====================================================================
MERGE INTO SNIPER_DB.RAW.HISTORICAL_LEADERBOARD AS target
USING (
    SELECT 
        $1 AS DATETIME, 
        $2::NUMBER(20, 6) AS OPEN, 
        $3::NUMBER(20, 6) AS HIGH, 
        $4::NUMBER(20, 6) AS LOW, 
        $5::NUMBER(20, 6) AS CLOSE, 
        $6::VARCHAR AS INSTRUMENT, 
        $7::VARCHAR AS TIMEFRAME, 
        $8::VARCHAR AS SOURCE
    FROM @SNIPER_DB.RAW.SNIPER_REPO/branches/main/data/raw_hourly_history.csv
    (FILE_FORMAT => 'SNIPER_DB.RAW.CSV_GITHUB_FORMAT')
    WHERE $1 IS NOT NULL AND $6 IS NOT NULL
) AS source
ON  target.INSTRUMENT = source.INSTRUMENT
AND target.TIMEFRAME = source.TIMEFRAME
AND target.DATETIME = source.DATETIME

-- If the row matches, update the price metrics (handles API delta recalculations/spikes)
WHEN MATCHED THEN
    UPDATE SET 
        target.OPEN = source.OPEN,
        target.HIGH = source.HIGH,
        target.LOW = source.LOW,
        target.CLOSE = source.CLOSE,
        target.SOURCE = source.SOURCE

-- If the row is brand new, append it cleanly to the ledger
WHEN NOT MATCHED THEN
    INSERT (DATETIME, OPEN, HIGH, LOW, CLOSE, INSTRUMENT, TIMEFRAME, SOURCE)
    VALUES (source.DATETIME, source.OPEN, source.HIGH, source.LOW, source.CLOSE, source.INSTRUMENT, source.TIMEFRAME, source.SOURCE);
