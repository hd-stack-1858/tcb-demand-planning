"""One-off: apply migration 015 to dev DB."""
from pathlib import Path
from dotenv import dotenv_values
import psycopg2

ROOT = Path(__file__).parent.parent.parent
cfg  = dotenv_values(ROOT / ".env.dev")

def _parse_url(url):
    s = url[len("postgresql://"):]
    ui, hi = s.rsplit("@", 1)
    user, pw = ui.split(":", 1)
    hp, db = hi.rsplit("/", 1)
    host, port = hp.rsplit(":", 1)
    return dict(host=host, port=int(port), dbname=db, user=user, password=pw, sslmode="require")

conn = psycopg2.connect(**_parse_url(cfg["DEV_DB_URL"]))
conn.autocommit = True
cur = conn.cursor()

# demand_forecasts doesn't exist in dev yet — create with correct (updated) schema
cur.execute("""
CREATE TABLE IF NOT EXISTS demand_forecasts (
  forecast_id     SERIAL PRIMARY KEY,
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  channel_id      INT  NOT NULL REFERENCES channels(channel_id),
  forecast_month  DATE NOT NULL,
  forecast_units  INT,
  confidence_lo   INT,
  confidence_hi   INT,
  model           TEXT NOT NULL DEFAULT 'VELOCITY_BASE',
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (sku_id, channel_id, forecast_month, model)
);
""")
print("demand_forecasts table created in dev DB with new constraint.")

# Verify
cur.execute("""
    SELECT constraint_name FROM information_schema.table_constraints
    WHERE table_name = 'demand_forecasts' AND constraint_type = 'UNIQUE'
""")
for row in cur.fetchall():
    print("  Constraint:", row[0])

cur.close()
conn.close()
