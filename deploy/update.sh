#!/usr/bin/env bash
# Apply a new version after `git pull`: dependencies, migrations, restart.
#   cd /opt/gmiremail && git pull && sudo deploy/update.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="/etc/gmiremail/gmiremail.env"

"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chmod -R a+rX "$APP_DIR"
runuser -u gmiremail -- bash -c "set -a; . '$ENV_FILE'; set +a; cd '$APP_DIR' && venv/bin/flask --app wsgi db upgrade"
systemctl restart gmiremail-web gmiremail-worker
sleep 2
systemctl --no-pager --lines=0 status gmiremail-web gmiremail-worker
