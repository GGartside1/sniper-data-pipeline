-- ====================================================================
-- 1. THE SYNC: Force Snowflake to pull the absolute latest commits from GitHub
-- ====================================================================
ALTER GIT REPOSITORY SNIPER_DB.RAW.SNIPER_REPO FETCH;


-- ====================================================================
-- 2. THE PURGE: Clean slate the target history table
-- ====================================================================
TRUNCATE TABLE SNIPER_DB.RAW.HISTORICAL_LEADERBOARD;


-- ====================================================================
-- 3. THE RE-IMPORT: Stream the freshly synced raw data file
-- ====================================================================
INSERT INTO SNIPER_DB.RAW.HISTORICAL_LEADERBOARD (
    DATETIME, 
    OPEN, 
    HIGH, 
    LOW, 
    CLOSE, 
    INSTRUMENT, 
    TIMEFRAME, 
    SOURCE
)
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
(FILE_FORMAT => 'SNIPER_DB.RAW.CSV_GITHUB_FORMAT');


-- ====================================================================
-- 4. THE AUDIT: Verify everything loaded all the way up to today (2026-05-27)
-- ====================================================================
SELECT 
    TIMEFRAME, 
    SOURCE, 
    COUNT(*) AS TOTAL_LOADED_ROWS,
    MIN(LEFT(DATETIME, 10)) AS DATA_FROM,
    MAX(LEFT(DATETIME, 10)) AS DATA_TO
FROM SNIPER_DB.RAW.HISTORICAL_LEADERBOARD 
GROUP BY TIMEFRAME, SOURCE
ORDER BY TIMEFRAME DESC;

-- List the file metadata directly inside your GitHub Stage
LIST @SNIPER_DB.RAW.SNIPER_REPO/branches/main/data/;
