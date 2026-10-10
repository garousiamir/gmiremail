#!/usr/bin/env bash
# Remove gmiremail from this server: everything deploy/install.sh set up.
#
# Usage (as root):
#   sudo /opt/gmiremail/deploy/uninstall.sh [--no-backup] [--keep-backups]
#        [--remove-packages] [--yes]
#
# By default a final full backup is saved to /root first, so you can restore
# it later (deploy/install.sh --restore <file>). Then it removes:
#   the web and worker services, the nginx site, the Let's Encrypt
#   certificate, the database and its user, /etc/gmiremail, the daily backup
#   job, the system user and the application directory.
#
#   --no-backup        Don't save a final backup first
#   --keep-backups     Keep the daily backups in /var/backups/gmiremail
#   --remove-packages  Also uninstall PostgreSQL, nginx, Postfix and OpenDKIM.
#                      Only use this if nothing else on the server needs them.
#   --yes              Don't ask for confirmation
set -euo pipefail

main() {
  local BACKUP=1 KEEP_BACKUPS=0 REMOVE_PACKAGES=0 ASSUME_YES=0 FINAL_BACKUP=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-backup) BACKUP=0 ;;
      --keep-backups) KEEP_BACKUPS=1 ;;
      --remove-packages) REMOVE_PACKAGES=1 ;;
      --yes|-y) ASSUME_YES=1 ;;
      -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
  done

  log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
  warn() { printf '\033[1;33mWARNING:\033[0m %s\n' "$*" >&2; }
  [[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }

  local APP_DIR APP_USER=gmiremail ENV_DIR=/etc/gmiremail ENV_FILE=/etc/gmiremail/gmiremail.env
  APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  local SITE=/etc/nginx/sites-available/gmiremail DOMAIN=""
  [[ -f "$SITE" ]] && DOMAIN="$(awk '$1 == "server_name" { gsub(";", "", $2); print $2; exit }' "$SITE")"
  if [[ -z "$DOMAIN" && -f "$ENV_FILE" ]]; then
    DOMAIN="$(sed -n 's#^TRACKING_DOMAIN=https\?://\([^/]*\).*#\1#p' "$ENV_FILE")"
  fi

  cat <<EOF

This permanently removes gmiremail from this server:
  - application:   $APP_DIR
  - settings:      $ENV_DIR
  - database:      PostgreSQL database and user "$APP_USER" (all accounts, subscribers, campaigns, analytics)
  - web:           nginx site${DOMAIN:+ for $DOMAIN} and its Let's Encrypt certificate
  - services:      gmiremail-web, gmiremail-worker, daily backup job
EOF
  [[ $BACKUP -eq 1 ]] && echo "A final backup is saved to /root first."
  [[ $BACKUP -eq 0 ]] && echo "NO final backup will be made (--no-backup)."
  [[ $KEEP_BACKUPS -eq 0 ]] && echo "Daily backups in /var/backups/gmiremail are deleted too (use --keep-backups to keep them)."
  [[ $REMOVE_PACKAGES -eq 1 ]] && echo "PostgreSQL, nginx, Postfix and OpenDKIM are uninstalled, with ALL their data and settings."
  if [[ $ASSUME_YES -eq 0 ]]; then
    local answer
    read -r -p $'\nType DELETE to continue: ' answer
    [[ "$answer" == "DELETE" ]] || { echo "Cancelled. Nothing was changed."; exit 1; }
  fi

  if [[ $BACKUP -eq 1 ]]; then
    log "Saving a final backup"
    local FILE
    FILE="/root/gmiremail-final-backup-$(date +%F-%H%M).tar.gz"
    if [[ -f "$ENV_FILE" && -x "$APP_DIR/venv/bin/flask" ]] && (umask 077; runuser -u "$APP_USER" -- sh -c \
        "set -a; . '$ENV_FILE'; set +a; cd '$APP_DIR' && venv/bin/flask --app wsgi backup create -o -" > "$FILE"); then
      FINAL_BACKUP="$FILE"
      echo "Saved $FILE ($(du -h "$FILE" | cut -f1)). Keep it if you may want your data back."
    else
      rm -f "$FILE"
      warn "The backup failed."
      if [[ $ASSUME_YES -eq 0 ]]; then
        local answer
        read -r -p "Continue WITHOUT a backup? Type DELETE to continue: " answer
        [[ "$answer" == "DELETE" ]] || { echo "Cancelled. Nothing was removed."; exit 1; }
      else
        echo "Stopping. Re-run with --no-backup to remove without a backup." >&2; exit 1
      fi
    fi
  fi

  log "Stopping and removing the services"
  systemctl disable --now gmiremail-web gmiremail-worker 2>/dev/null || true
  rm -f /etc/systemd/system/gmiremail-web.service /etc/systemd/system/gmiremail-worker.service
  systemctl daemon-reload 2>/dev/null || true
  rm -f /etc/cron.daily/gmiremail-backup

  log "Removing the nginx site"
  rm -f /etc/nginx/sites-enabled/gmiremail "$SITE"
  if command -v nginx >/dev/null && systemctl is-active --quiet nginx; then
    if nginx -t 2>/dev/null; then systemctl reload nginx; else warn "nginx config test failed; check 'nginx -t'"; fi
  fi
  if [[ -n "$DOMAIN" ]] && command -v certbot >/dev/null && [[ -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
    log "Deleting the certificate for $DOMAIN"
    certbot delete --cert-name "$DOMAIN" --non-interactive || warn "Could not delete the certificate"
  fi

  if command -v psql >/dev/null && systemctl is-active --quiet postgresql; then
    log "Dropping the database"
    runuser -u postgres -- psql -q -c "DROP DATABASE IF EXISTS $APP_USER WITH (FORCE)" 2>/dev/null \
      || runuser -u postgres -- psql -q -c "DROP DATABASE IF EXISTS $APP_USER"
    runuser -u postgres -- psql -q -c "DROP ROLE IF EXISTS $APP_USER"
  fi

  if [[ -f /etc/opendkim.conf ]] && grep -q 'Managed by gmiremail' /etc/opendkim.conf && [[ $REMOVE_PACKAGES -eq 0 ]]; then
    log "Detaching DKIM signing from Postfix"
    postconf -X smtpd_milters non_smtpd_milters 2>/dev/null || true
    systemctl disable --now opendkim 2>/dev/null || true
    systemctl reload postfix 2>/dev/null || true
  fi

  if [[ $REMOVE_PACKAGES -eq 1 ]]; then
    log "Uninstalling PostgreSQL, nginx, Postfix and OpenDKIM"
    export DEBIAN_FRONTEND=noninteractive
    apt-get purge -y -q 'postgresql*' nginx nginx-common postfix opendkim opendkim-tools certbot || true
    apt-get autoremove -y -q || true
    rm -rf /etc/opendkim /etc/opendkim.conf /var/lib/postgresql /etc/postgresql
  fi

  log "Removing files and the system user"
  rm -rf "$ENV_DIR"
  [[ $KEEP_BACKUPS -eq 0 ]] && rm -rf /var/backups/gmiremail
  rmdir /var/www/letsencrypt 2>/dev/null || true
  if id -u "$APP_USER" >/dev/null 2>&1; then userdel "$APP_USER" 2>/dev/null || true; fi
  cd /
  case "$APP_DIR" in
    /|/root|/home|/usr|/etc|/var|/opt) warn "Not deleting $APP_DIR; remove it yourself." ;;
    *) rm -rf "$APP_DIR" ;;
  esac

  log "gmiremail has been removed"
  [[ -n "$FINAL_BACKUP" ]] && echo "Your final backup: $FINAL_BACKUP (restore with deploy/install.sh --restore)"
  [[ -n "$DOMAIN" ]] && echo "You can now delete the DNS records for $DOMAIN (A, SPF, DKIM, DMARC) if you no longer need them."
  return 0
}

main "$@"
