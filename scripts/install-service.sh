#!/usr/bin/env bash
# Install or refresh the tennis-mtl systemd unit. Idempotent — re-run after
# pulling changes to scripts/tennis-mtl.service.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DEST=/etc/systemd/system/tennis-mtl.service

sed "s|TENNIS_MTL_DIR|${REPO_DIR}|g" "${REPO_DIR}/scripts/tennis-mtl.service" \
    | sed "/\[Service\]/a User=$(whoami)" \
    | sudo tee "${UNIT_DEST}" > /dev/null

sudo systemctl daemon-reload
sudo systemctl restart tennis-mtl
sudo systemctl status tennis-mtl --no-pager
