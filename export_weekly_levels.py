import os
import json
import snowflake.connector
from datetime import datetime

def export_current_week_levels():
    print(f"🎯 Starting Weekly Anchor Level Export at {datetime.now()}")
    
    # Dynamically pick up your dev schema or default to analytics if running in production
    target_schema = os.getenv('SNOWFLAKE_SCHEMA', 'DBT_GGARTSIDE')
    print(f"📦 Routing extraction through target schema: {target_schema}")

    # Connect using environmental variables for security
    ctx = snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        warehouse='COMPUTE_WH',
        database='SNIPER_DB',
        schema=target_schema
    )
    cs = ctx.cursor()
    
    # 1. Complete query capturing all requested execution brackets
    query = f"""
    WITH latest_anchor AS (
        SELECT 
            INSTRUMENT,
            RECORD_WEEK,
            CURRENT_WEEK_OPEN,
            PIP_UNIT,
            BASELINE_UP_MEAN_PRICE,
            BASELINE_DN_PRICE,
            UP_FAIL_50, UP_FAIL_60, UP_FAIL_75, UP_FAIL_90,
            DN_FAIL_50, DN_FAIL_60, DN_FAIL_75, DN_FAIL_90,
            ROW_NUMBER() OVER (PARTITION BY INSTRUMENT ORDER BY RECORD_WEEK DESC) as rn
        FROM SNIPER_DB.{target_schema}.FCT_SNIPER_LEVELS
    )
    SELECT 
        INSTRUMENT, 
        RECORD_WEEK, 
        CURRENT_WEEK_OPEN, 
        PIP_UNIT,
        BASELINE_UP_MEAN_PRICE, 
        BASELINE_DN_PRICE, 
        UP_FAIL_50, UP_FAIL_60, UP_FAIL_75, UP_FAIL_90,
        DN_FAIL_50, DN_FAIL_60, DN_FAIL_75, DN_FAIL_90
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
        
        # 2. Map the expanded structural array index safely
        for row in rows:
            # Determine dynamic decimal precision depending on asset class
            inst_name = str(row[0])
            decimals = 2 if any(idx in inst_name for idx in ["SPX", "DAX"]) else 5

            export_data["levels"][inst_name] = {
                "trading_week": str(row[1]),
                "weekly_open": round(float(row[2]), decimals),
                "unit_type": str(row[3]),
                "baseline_up_mean": round(float(row[4]), decimals),
                "baseline_dn_mean": round(float(row[5]), decimals),
                "sniper_targets": {
                    "upside": {
                        "fail_50": round(float(row[6]), decimals),
                        "fail_60": round(float(row[7]), decimals),
                        "fail_75": round(float(row[8]), decimals),
                        "fail_90": round(float(row[9]), decimals)
                    },
                    "downside": {
                        "fail_50": round(float(row[10]), decimals),
                        "fail_60": round(float(row[11]), decimals),
                        "fail_75": round(float(row[12]), decimals),
                        "fail_90": round(float(row[13]), decimals)
                    }
                }
            }
        
        # Check and enforce local directory layout
        os.makedirs('Data', exist_ok=True)

        # Save explicitly as a clean JSON asset
        with open('Data/current_week_levels.json', 'w') as f:
            json.dump(export_data, f, indent=4)
            
        print("✅ current_week_levels.json generated successfully with all asymmetric intervals mapped.")
        
    except Exception as e:
        print(f"❌ Export failed: {str(e)}")
        raise e
    finally:
        cs.close()
        ctx.close()

if __name__ == "__main__":
    export_current_week_levels()
