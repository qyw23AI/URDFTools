#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$root" != "$HOME/URDFTools" ]]; then
  echo "Install the repository at $HOME/URDFTools first" >&2
  exit 2
fi
mkdir -p "$HOME/.config/systemd/user"
cp "$root/systemd/urdftools-dev.service" "$root/systemd/urdftools-dev.timer" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now urdftools-dev.timer
systemctl --user status urdftools-dev.timer --no-pager
python3 "$root/scripts/verify_scheduler_timer.py"
