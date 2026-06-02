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
    query = """
    WITH latest_anchor AS (
        SELECT 
            INSTRUMENT,
            TRADING_WEEK,
            PIP_MULTIPLIER,
            WEEKLY_HIGH_LEVEL,
            WEEKLY_LOW_LEVEL,
            ROW_NUMBER() OVER (PARTITION BY INSTRUMENT ORDER BY TRADING_WEEK DESC) as rn
        FROM SNIPER_DB.ANALYTICS.FCT_SNIPER_LEVELS
    )
    SELECT INSTRUMENT, TRADING_WEEK, PIP_MULTIPLIER, WEEKLY_HIGH_LEVEL, WEEKLY_LOW_LEVEL
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
        
        for row in rows:
            export_data["levels"][row[0]] = {
                "trading_week": str(row[1]),
                "pip_multiplier": float(row[2]),
                "high_level": float(row[3]),
                "low_level": float(row[4])
            }
        
        # Save explicitly as a clean JSON asset
        with open('current_week_levels.json', 'w') as f:
            json.dump(export_data, f, indent=4)
            
        print("✅ current_week_levels.json generated successfully.")
        
    except Exception as e:
        print(f"❌ Export failed: {str(e)}")
        raise e
    finally:
        cs.close()
        ctx.close()

if __name__ == "__main__":
    export_current_week_levels()
