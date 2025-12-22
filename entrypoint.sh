#!/usr/bin/env sh
set -e

echo "Waiting for Postgres..."
python - <<'PY'
import os, time
import psycopg

url = os.environ["DATABASE_DSN"]
for i in range(60):
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
        print("Postgres is ready")
        break
    except Exception as e:
        time.sleep(1)
else:
    raise SystemExit("Postgres not ready after 60s")
PY

echo "Running migrations..."
alembic upgrade head

echo "Starting bot..."
exec python main.py
