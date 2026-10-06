#!/usr/bin/env sh
set -eu

python -m app.deploy validate-config
python -m app.deploy wait-for-db
python -m alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
