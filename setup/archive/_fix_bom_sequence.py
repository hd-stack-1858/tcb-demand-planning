import psycopg2
from pathlib import Path
from dotenv import dotenv_values
cfg = dotenv_values(str(Path(__file__).parent.parent / '.env.dev'))
conn = psycopg2.connect(cfg['DEV_DB_URL'])
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT setval(pg_get_serial_sequence('bom','bom_id'), (SELECT MAX(bom_id) FROM bom))")
print('bom sequence reset on dev')
conn.close()
