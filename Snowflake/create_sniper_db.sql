-- 1. Explicitly switch to the ACCOUNTADMIN role to ensure max permissions
USE ROLE ACCOUNTADMIN;

-- 2. Hard-force creation of the database boundaries
CREATE DATABASE IF NOT EXISTS SNIPER_DB;
CREATE SCHEMA IF NOT EXISTS SNIPER_DB.RAW;

-- 3. Lock the current session context down tightly
USE WAREHOUSE COMPUTE_WH;
USE DATABASE SNIPER_DB;
USE SCHEMA RAW;

-- 4. Create the File Format using a fully-qualified name so it cannot fail
CREATE OR REPLACE FILE FORMAT SNIPER_DB.RAW.CSV_GITHUB_FORMAT
  TYPE = 'CSV'
  FIELD_DELIMITER = ','
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('', 'NULL')
  EMPTY_FIELD_AS_NULL = TRUE
  ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE;

  -- set warehouse to cut-off after 60 seconds to avoid idele compute
ALTER WAREHOUSE COMPUTE_WH SET 
    AUTO_SUSPEND = 60, 
    AUTO_RESUME = TRUE;

    ALTER WAREHOUSE COMPUTE_WH SET WAREHOUSE_SIZE = 'XSMALL';
