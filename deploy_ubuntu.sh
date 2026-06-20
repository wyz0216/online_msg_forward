#!/usr/bin/env bash
set -euo pipefail

APP_NAME="online_msg_forward"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
CLEANUP_SERVICE_FILE="/etc/systemd/system/${APP_NAME}-cleanup.service"
CLEANUP_TIMER_FILE="/etc/systemd/system/${APP_NAME}-cleanup.timer"
PORT="${PORT:-8000}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash deploy_ubuntu.sh"
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${SRC_DIR}"
ENV_FILE="${APP_DIR}/.env"

if systemctl is-active --quiet "${APP_NAME}.service"; then
  systemctl stop "${APP_NAME}.service"
fi
if systemctl is-active --quiet "${APP_NAME}-cleanup.timer"; then
  systemctl stop "${APP_NAME}-cleanup.timer"
fi

apt-get update
apt-get install -y python3-venv python3-pip

mkdir -p "${APP_DIR}/data" "${APP_DIR}/uploads"

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

if [[ -f "${ENV_FILE}" ]]; then
  echo "Keeping existing ${ENV_FILE}"
else
  SECRET_KEY="$("${APP_DIR}/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  CLEANUP_TOKEN="$("${APP_DIR}/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  cat > "${ENV_FILE}" <<ENV
SECRET_KEY=${SECRET_KEY}
DATABASE_PATH=${APP_DIR}/data/app.db
UPLOAD_DIR=${APP_DIR}/uploads
MAX_UPLOAD_MB=20
ALLOW_REGISTRATION=true
CLEANUP_TOKEN=${CLEANUP_TOKEN}
HOST=127.0.0.1
PORT=${PORT}
ENV
fi
chmod 600 "${ENV_FILE}"

cat > "${SERVICE_FILE}" <<SERVICE
[Unit]
Description=Online Message Forward FastAPI app
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${APP_DIR}/.venv/bin/python -m uvicorn app.main:app --host \${HOST} --port \${PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE

cat > "${CLEANUP_SERVICE_FILE}" <<SERVICE
[Unit]
Description=Clean expired Online Message Forward records

[Service]
Type=oneshot
EnvironmentFile=${ENV_FILE}
ExecStart=/bin/sh -c 'python3 -c "import os, urllib.request; req = urllib.request.Request(\"http://127.0.0.1:\" + os.environ[\"PORT\"] + \"/cleanup\", method=\"POST\", headers={\"X-Cleanup-Token\": os.environ[\"CLEANUP_TOKEN\"]}); urllib.request.urlopen(req, timeout=10).read()"'
SERVICE

cat > "${CLEANUP_TIMER_FILE}" <<TIMER
[Unit]
Description=Run Online Message Forward cleanup every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Unit=${APP_NAME}-cleanup.service

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now "${APP_NAME}.service"
systemctl enable --now "${APP_NAME}-cleanup.timer"
systemctl restart "${APP_NAME}.service"

echo "${APP_NAME} deployed."
echo "App directory: ${APP_DIR}"
echo "App listens on http://127.0.0.1:${PORT}"
echo "Configure your own nginx reverse proxy to this local address."
echo "Service status: systemctl status ${APP_NAME}.service"
echo "Logs: journalctl -u ${APP_NAME}.service -f"
