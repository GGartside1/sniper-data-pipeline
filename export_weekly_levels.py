import os
import json
import snowflake.connector
from datetime import datetime

def export_current_week_levels():
    print(f"🎯 Starting Weekly Anchor Level Export at {datetime.now()}")
    
    # Connect using environmental variables for security
    ctx = snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        warehouse='COMPUTE_WH',
        database='SNIPER_DB',
        schema='ANALYTICS'
    )
    cs = ctx.cursor()
    
    # Query to fetch the most recent metrics for each instrument
# 1. Update the SQL query to target your exact dbt model outputs
    query = """
    WITH latest_anchor AS (
        SELECT 
            INSTRUMENT,
            RECORD_WEEK,
            CURRENT_WEEK_OPEN,
            PIP_UNIT,
            BASELINE_UP_MEAN_PRICE,
            BASELINE_DN_PRICE,
            UP_FAIL_90,
            DN_FAIL_90,
            ROW_NUMBER() OVER (PARTITION BY INSTRUMENT ORDER BY RECORD_WEEK DESC) as rn
        FROM SNIPER_DB.ANALYTICS.FCT_SNIPER_LEVELS
    )
    SELECT 
        INSTRUMENT, 
        RECORD_WEEK, 
        CURRENT_WEEK_OPEN, 
        PIP_UNIT,
        BASELINE_UP_MEAN_PRICE, 
        BASELINE_DN_PRICE, 
        UP_FAIL_90, 
        DN_FAIL_90
    FROM latest_anchor
    WHERE rn = 1;
    """
    
    try:
        cs.execute(query)
        rows = cs.fetchall()
        
        export_data = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "levels": {}
        }
        
        # 2. Map the data structure to match your exact columns
        for row in rows:
            export_data["levels"][row[0]] = {
                "trading_week": str(row[1]),
                "weekly_open": float(row[2]),
                "unit_type": str(row[3]),
                "baseline_up_mean": float(row[4]),
                "baseline_dn_mean": float(row[5]),
                "sniper_high_level_90": float(row[6]),
                "sniper_low_level_90": float(row[7])
            }
        
        # Save explicitly as a clean JSON asset
        with open('current_week_levels.json', 'w') as f:
            json.dump(export_data, f, indent=4)
            
        print("✅ current_week_levels.json generated successfully using fct_sniper_levels definitions.")
        
    except Exception as e:
        print(f"❌ Export failed: {str(e)}")
        raise e
    finally:
        cs.close()
        ctx.close()

if __name__ == "__main__":
    export_current_week_levels()
