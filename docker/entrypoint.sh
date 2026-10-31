#!/bin/sh
set -e

python manage.py wait_for_db
python manage.py migrate --noinput
python manage.py ensure_admin

if [ "$SEED_DEMO" = "true" ]; then
  python manage.py seed_demo
fi

exec "$@"
