#!/usr/bin/env bash
# Invoked by the launcher with sudo/pkexec; touches only quiz-labelled rules.
set -euo pipefail
iface=$1 subnet=$2 port=$3
[[ "$iface" =~ ^[a-zA-Z0-9_.:-]+$ && "$subnet" =~ ^[0-9.]+/[0-9]+$ && "$port" =~ ^[0-9]+$ ]] || exit 2
if ! command -v avahi-publish >/dev/null || ! /usr/bin/python3 -c "import dbus" 2>/dev/null; then
    if command -v omarchy >/dev/null; then omarchy pkg add avahi python-dbus
    else pacman -S --needed --noconfirm avahi python-dbus; fi
fi
systemctl start avahi-daemon.service
if command -v ufw >/dev/null; then
    # Remove only this application's prior labelled allowances before installing the selected subnet.
    mapfile -t rules < <(ufw status numbered | sed -n '/# jpcs-quiz /s/^\[ *\([0-9]*\)\].*/\1/p' | sort -rn)
    for number in "${rules[@]}"; do ufw --force delete "$number"; done
    ufw allow in on "$iface" from "$subnet" to any port "$port" proto tcp comment 'jpcs-quiz http'
    ufw allow in on "$iface" from "$subnet" to any port 5353 proto udp comment 'jpcs-quiz mdns'
    ufw status
else
    echo 'No supported firewall manager found. Configure your firewall for the selected LAN before starting.' >&2
    exit 1
fi
