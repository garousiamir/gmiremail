#!/usr/bin/env bash
# Create a DKIM key for another sender domain and print the DNS record.
#   sudo deploy/add-dkim-domain.sh example.com [selector]
set -euo pipefail
DOMAIN="${1:?usage: add-dkim-domain.sh <domain> [selector]}"
SELECTOR="${2:-mail}"
QUIET="${3:-}"
[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }

KEY_DIR="/etc/opendkim/keys/$DOMAIN"
mkdir -p /etc/opendkim/keys
touch /etc/opendkim/KeyTable /etc/opendkim/SigningTable
if [[ ! -f "$KEY_DIR/$SELECTOR.private" ]]; then
  mkdir -p "$KEY_DIR"
  opendkim-genkey -b 2048 -d "$DOMAIN" -s "$SELECTOR" -D "$KEY_DIR"
fi
chown -R opendkim:opendkim /etc/opendkim/keys
chmod 700 "$KEY_DIR"
chmod 600 "$KEY_DIR/$SELECTOR.private"

# Copy readable by the app so the keys are included in Settings -> Backup
if id -u gmiremail >/dev/null 2>&1; then
  install -d -m 750 -o root -g gmiremail /etc/gmiremail/dkim "/etc/gmiremail/dkim/$DOMAIN"
  install -m 640 -o root -g gmiremail "$KEY_DIR/$SELECTOR.private" "/etc/gmiremail/dkim/$DOMAIN/$SELECTOR.private"
  [[ -f "$KEY_DIR/$SELECTOR.txt" ]] && install -m 640 -o root -g gmiremail "$KEY_DIR/$SELECTOR.txt" "/etc/gmiremail/dkim/$DOMAIN/$SELECTOR.txt"
fi

KEY_ENTRY="$SELECTOR._domainkey.$DOMAIN $DOMAIN:$SELECTOR:$KEY_DIR/$SELECTOR.private"
SIGN_ENTRY="*@$DOMAIN $SELECTOR._domainkey.$DOMAIN"
grep -qxF "$KEY_ENTRY" /etc/opendkim/KeyTable || echo "$KEY_ENTRY" >> /etc/opendkim/KeyTable
grep -qxF "$SIGN_ENTRY" /etc/opendkim/SigningTable || echo "$SIGN_ENTRY" >> /etc/opendkim/SigningTable

if [[ "$QUIET" != "--quiet" ]]; then
  systemctl restart opendkim
  TXT="$(tr -d '\n' < "$KEY_DIR/$SELECTOR.txt" | sed -e 's/.*([[:space:]]*//' -e 's/[[:space:]]*).*//' -e 's/"[[:space:]]*"//g' -e 's/"//g')"
  echo "Add this DNS record, plus SPF/DMARC for $DOMAIN (see docs/DEPLOYMENT.md):"
  echo
  echo "  $SELECTOR._domainkey.$DOMAIN.  TXT  \"$TXT\""
fi
