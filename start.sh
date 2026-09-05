#!/bin/bash
cd /var/www/lista-clienti || exit 1

set -a
source /var/www/lista-clienti/.env
set +a

exec /var/www/lista-clienti/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8001 app:app
