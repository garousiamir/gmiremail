#!/usr/bin/env bash
# gmiremail single-server installer for Ubuntu 22.04/24.04 and Debian 12.
#
# Installs and configures, on this one machine:
#   PostgreSQL, the web app (gunicorn + systemd), the background worker,
#   nginx with a Let's Encrypt certificate, Postfix (send-only) with
#   OpenDKIM signing, and daily database backups.
#
# Usage (from the repository checkout, as root):
#   sudo deploy/install.sh --domain mail.example.com --email you@example.com \
#        [--mail-domain example.com] [--admin-email you@example.com]
#        [--restore gmiremail-backup.tar.gz] [--no-postfix] [--skip-certbot]
#
# Safe to re-run: existing secrets, database, DKIM keys and certificates are kept.
set -euo pipefail

DOMAIN=""
LE_EMAIL=""
MAIL_DOMAIN=""
ADMIN_EMAIL=""
RESTORE_FILE=""
WITH_POSTFIX=1
WITH_CERTBOT=1
APP_USER="gmiremail"
PORT="8000"
WORKERS="3"
DKIM_SELECTOR="mail"

usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) LE_EMAIL="$2"; shift 2 ;;
    --mail-domain) MAIL_DOMAIN="$2"; shift 2 ;;
    --admin-email) ADMIN_EMAIL="$2"; shift 2 ;;
    --restore) RESTORE_FILE="$(realpath "$2")"; shift 2 ;;
    --no-postfix) WITH_POSTFIX=0; shift ;;
    --skip-certbot) WITH_CERTBOT=0; shift ;;
    --port) PORT="$2"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
done

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root (sudo)."
[[ -f /etc/debian_version ]] || die "This installer supports Debian/Ubuntu only."
[[ -n "$DOMAIN" ]] || die "--domain is required (the hostname that serves the dashboard, e.g. mail.example.com)."
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "--domain does not look like a hostname: $DOMAIN"
if [[ $WITH_CERTBOT -eq 1 && -z "$LE_EMAIL" ]]; then
  die "--email is required for Let's Encrypt (or pass --skip-certbot)."
fi
MAIL_DOMAIN="${MAIL_DOMAIN:-$DOMAIN}"
[[ -z "$RESTORE_FILE" || -f "$RESTORE_FILE" ]] || die "Backup file not found: $RESTORE_FILE"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$APP_DIR/deploy"
ENV_DIR="/etc/gmiremail"
ENV_FILE="$ENV_DIR/gmiremail.env"
[[ -f "$APP_DIR/wsgi.py" ]] || die "Run this script from inside the gmiremail repository."

SERVER_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") print $(i+1)}' | head -1)"

# --------------------------------------------------------------- packages
log "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
PACKAGES=(python3 python3-venv python3-dev build-essential libpq-dev postgresql nginx certbot dnsutils ca-certificates)
if [[ $WITH_POSTFIX -eq 1 ]]; then
  echo "postfix postfix/main_mailer_type select Internet Site" | debconf-set-selections
  echo "postfix postfix/mailname string $MAIL_DOMAIN" | debconf-set-selections
  PACKAGES+=(postfix opendkim opendkim-tools)
fi
apt-get install -y -q "${PACKAGES[@]}"

# ------------------------------------------------------------ app + venv
log "Setting up the application in $APP_DIR"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chmod -R a+rX "$APP_DIR"

# -------------------------------------------------------------- database
log "Configuring PostgreSQL"
systemctl enable --now postgresql
gen_secret() { python3 -c 'import secrets; print(secrets.token_hex(32))'; }
if [[ -f "$ENV_FILE" ]]; then
  # Re-use the existing password so the database keeps working
  DB_PASS="$(sed -n 's#^DATABASE_URL=postgresql://[^:]*:\([^@]*\)@.*#\1#p' "$ENV_FILE")"
  [[ -n "$DB_PASS" ]] || die "Could not read the database password from $ENV_FILE"
else
  DB_PASS="$(gen_secret)"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$APP_USER'" | grep -q 1; then
  runuser -u postgres -- psql -q -c "CREATE ROLE $APP_USER LOGIN PASSWORD '$DB_PASS'"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='$APP_USER'" | grep -q 1; then
  runuser -u postgres -- createdb -O "$APP_USER" "$APP_USER"
fi

# ----------------------------------------------------------- environment
mkdir -p "$ENV_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  log "Writing $ENV_FILE (secrets generated)"
  if [[ $WITH_POSTFIX -eq 1 ]]; then
    SMTP_HOST=127.0.0.1; SMTP_PORT=25; SMTP_TLS=False
  else
    SMTP_HOST=smtp.gmail.com; SMTP_PORT=587; SMTP_TLS=True
  fi
  umask 027
  cat > "$ENV_FILE" <<ENV
# gmiremail production settings (read by the systemd services)
FLASK_ENV=production
SECRET_KEY=$(gen_secret)
JWT_SECRET_KEY=$(gen_secret)
DATABASE_URL=postgresql://$APP_USER:$DB_PASS@localhost:5432/$APP_USER
AUTO_CREATE_TABLES=False

# Jobs run in gmiremail-worker.service, not in the web workers
ENABLE_SCHEDULER=False
QUEUE_PROCESSING_INTERVAL=10

# Behind nginx: trust one proxy for client IP / https
TRUSTED_PROXIES=1
TRACKING_DOMAIN=https://$DOMAIN
ENABLE_TRACKING=True

# Defaults for new accounts (each business can change its SMTP in Settings)
DEFAULT_SMTP_HOST=$SMTP_HOST
DEFAULT_SMTP_PORT=$SMTP_PORT
DEFAULT_SMTP_TLS=$SMTP_TLS

# Sending limits: keep these low while a new server IP warms up
DAILY_EMAIL_LIMIT=500
MAX_EMAILS_PER_MINUTE=20
MAX_EMAIL_BATCH_SIZE=100
MAX_RETRY_ATTEMPTS=3
MAX_SOFT_BOUNCES=3
EMAIL_LOG_RETENTION_DAYS=365
AUTH_RATE_LIMIT_PER_MINUTE=20

# Who may download full backups (Settings -> Backup). Empty = the first account created.
ADMIN_EMAILS=$ADMIN_EMAIL
# Readable copy of the DKIM keys so they are included in backups
DKIM_BACKUP_DIR=$ENV_DIR/dkim
ENV
  umask 022
else
  log "Keeping existing $ENV_FILE"
  grep -q '^DKIM_BACKUP_DIR=' "$ENV_FILE" || echo "DKIM_BACKUP_DIR=$ENV_DIR/dkim" >> "$ENV_FILE"
  grep -q '^ADMIN_EMAILS=' "$ENV_FILE" || echo "ADMIN_EMAILS=$ADMIN_EMAIL" >> "$ENV_FILE"
  [[ -n "$ADMIN_EMAIL" ]] && sed -i "s|^ADMIN_EMAILS=.*|ADMIN_EMAILS=$ADMIN_EMAIL|" "$ENV_FILE"
  grep -q "^TRACKING_DOMAIN=https://$DOMAIN\$" "$ENV_FILE" || \
    warn "TRACKING_DOMAIN in $ENV_FILE is not https://$DOMAIN; edit it if the hostname changed."
fi
chown root:"$APP_USER" "$ENV_DIR" "$ENV_FILE"
chmod 750 "$ENV_DIR"
chmod 640 "$ENV_FILE"

log "Running database migrations"
runuser -u "$APP_USER" -- bash -c "set -a; . '$ENV_FILE'; set +a; cd '$APP_DIR' && venv/bin/flask --app wsgi db upgrade"

# --------------------------------------------------------------- systemd
log "Installing systemd services"
# Only listen on IPv6 when the host has it (nginx refuses to start otherwise)
IPV6_PREFIX="# "; [[ -f /proc/net/if_inet6 ]] && IPV6_PREFIX=""
render() {
  sed -e "s|@IPV6@|$IPV6_PREFIX|g" -e "s#@APP_DIR@#$APP_DIR#g" -e "s#@ENV_FILE@#$ENV_FILE#g" -e "s#@APP_USER@#$APP_USER#g" \
      -e "s#@PORT@#$PORT#g" -e "s#@WORKERS@#$WORKERS#g" -e "s#@DOMAIN@#$DOMAIN#g" "$1"
}
render "$DEPLOY_DIR/systemd/gmiremail-web.service" > /etc/systemd/system/gmiremail-web.service
render "$DEPLOY_DIR/systemd/gmiremail-worker.service" > /etc/systemd/system/gmiremail-worker.service
systemctl daemon-reload
systemctl enable gmiremail-web gmiremail-worker >/dev/null
systemctl restart gmiremail-web gmiremail-worker

# ----------------------------------------------------------------- nginx
log "Configuring nginx for $DOMAIN"
mkdir -p /var/www/letsencrypt
SITE=/etc/nginx/sites-available/gmiremail
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
if [[ -f "$CERT_DIR/fullchain.pem" ]]; then
  render "$DEPLOY_DIR/nginx/gmiremail-https.conf" > "$SITE"
else
  render "$DEPLOY_DIR/nginx/gmiremail-http.conf" > "$SITE"
fi
ln -sf "$SITE" /etc/nginx/sites-enabled/gmiremail
nginx -t
systemctl enable nginx >/dev/null
systemctl reload nginx || systemctl restart nginx

if [[ $WITH_CERTBOT -eq 1 && ! -f "$CERT_DIR/fullchain.pem" ]]; then
  log "Requesting a Let's Encrypt certificate for $DOMAIN"
  RESOLVED="$(dig +short A "$DOMAIN" | tail -1)"
  if [[ -n "$SERVER_IP" && "$RESOLVED" != "$SERVER_IP" ]]; then
    warn "$DOMAIN resolves to '${RESOLVED:-nothing}', but this server's IP looks like $SERVER_IP."
    warn "If the certificate request fails, fix the DNS A record and re-run this script."
  fi
  if certbot certonly --webroot -w /var/www/letsencrypt -d "$DOMAIN" --email "$LE_EMAIL" \
      --agree-tos --non-interactive --deploy-hook "systemctl reload nginx"; then
    render "$DEPLOY_DIR/nginx/gmiremail-https.conf" > "$SITE"
    nginx -t && systemctl reload nginx
  else
    warn "Certificate request failed; the site is running on plain HTTP for now. Re-run this script once DNS is correct."
  fi
fi

# ------------------------------------------------------- postfix + DKIM
if [[ $WITH_POSTFIX -eq 1 ]]; then
  log "Configuring Postfix (send-only) and OpenDKIM"
  postconf -e \
    "myhostname = $DOMAIN" \
    "myorigin = $MAIL_DOMAIN" \
    "mydestination = localhost" \
    "inet_interfaces = loopback-only" \
    "inet_protocols = ipv4" \
    "mynetworks = 127.0.0.0/8" \
    "smtpd_tls_security_level = none" \
    "smtp_tls_security_level = may" \
    "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt" \
    "smtp_tls_loglevel = 1" \
    "milter_default_action = accept" \
    "milter_protocol = 6" \
    "smtpd_milters = inet:127.0.0.1:8891" \
    "non_smtpd_milters = inet:127.0.0.1:8891"

  mkdir -p /etc/opendkim/keys
  touch /etc/opendkim/KeyTable /etc/opendkim/SigningTable /etc/opendkim/TrustedHosts
  grep -qx "127.0.0.1" /etc/opendkim/TrustedHosts || printf '127.0.0.1\nlocalhost\n' >> /etc/opendkim/TrustedHosts
  cat > /etc/opendkim.conf <<CONF
# Managed by gmiremail deploy/install.sh
Syslog                  yes
UMask                   007
Mode                    s
Canonicalization        relaxed/simple
OversignHeaders         From
KeyTable                refile:/etc/opendkim/KeyTable
SigningTable            refile:/etc/opendkim/SigningTable
ExternalIgnoreList      refile:/etc/opendkim/TrustedHosts
InternalHosts           refile:/etc/opendkim/TrustedHosts
Socket                  inet:8891@127.0.0.1
PidFile                 /run/opendkim/opendkim.pid
UserID                  opendkim
CONF
  # Debian/Ubuntu also take the socket from /etc/default/opendkim
  if [[ -f /etc/default/opendkim ]]; then
    sed -i 's|^SOCKET=.*|SOCKET=inet:8891@127.0.0.1|' /etc/default/opendkim
    grep -q '^SOCKET=' /etc/default/opendkim || echo 'SOCKET=inet:8891@127.0.0.1' >> /etc/default/opendkim
    [[ -x /lib/opendkim/opendkim.service.generate ]] && /lib/opendkim/opendkim.service.generate && systemctl daemon-reload
  fi
  "$DEPLOY_DIR/add-dkim-domain.sh" "$MAIL_DOMAIN" "$DKIM_SELECTOR" --quiet
  systemctl enable opendkim postfix >/dev/null
  systemctl restart opendkim postfix

  if ! timeout 8 bash -c 'exec 3<>/dev/tcp/gmail-smtp-in.l.google.com/25' 2>/dev/null; then
    warn "Outbound port 25 seems BLOCKED. Many cloud providers block it by default; ask your provider"
    warn "to unblock it, or re-run with --no-postfix and use an external SMTP service."
  fi
fi

# --------------------------------------------------------------- backups
log "Installing daily full backups (/var/backups/gmiremail, kept 14 days)"
install -d -m 700 /var/backups/gmiremail
cat > /etc/cron.daily/gmiremail-backup <<CRON
#!/bin/sh
# Daily full backup, same format as Settings -> Backup (installed by deploy/install.sh)
set -e
umask 077
runuser -u $APP_USER -- sh -c "set -a; . '$ENV_FILE'; set +a; cd '$APP_DIR' && venv/bin/flask --app wsgi backup create -o -" \\
  > /var/backups/gmiremail/gmiremail-backup-\$(date +%F).tar.gz
find /var/backups/gmiremail -name 'gmiremail-*' -mtime +14 -delete
CRON
chmod 755 /etc/cron.daily/gmiremail-backup

# --------------------------------------------------------------- restore
if [[ -n "$RESTORE_FILE" ]]; then
  log "Restoring backup $RESTORE_FILE"
  "$DEPLOY_DIR/restore.sh" "$RESTORE_FILE" --yes
fi

# --------------------------------------------------------------- summary
sleep 2
systemctl is-active --quiet gmiremail-web || warn "gmiremail-web is not running: journalctl -u gmiremail-web"
systemctl is-active --quiet gmiremail-worker || warn "gmiremail-worker is not running: journalctl -u gmiremail-worker"
SCHEME=http; [[ -f "$CERT_DIR/fullchain.pem" ]] && SCHEME=https

log "Done"
cat <<SUMMARY

Dashboard:   $SCHEME://$DOMAIN/
Settings:    $ENV_FILE   (restart after editing: systemctl restart gmiremail-web gmiremail-worker)
Logs:        journalctl -u gmiremail-web -u gmiremail-worker -f
Update:      cd $APP_DIR && git pull && sudo deploy/update.sh
SUMMARY

if [[ $WITH_POSTFIX -eq 1 ]]; then
  IP_SHOWN="${SERVER_IP:-<server IP>}"
  DKIM_TXT="$(tr -d '\n' < "/etc/opendkim/keys/$MAIL_DOMAIN/$DKIM_SELECTOR.txt" | sed -e 's/.*([[:space:]]*//' -e 's/[[:space:]]*).*//' -e 's/"[[:space:]]*"//g' -e 's/"//g')"
  cat <<EOF_DNS

DNS records to add at your DNS provider (needed for inbox delivery):

  $DOMAIN.                     A     $IP_SHOWN
  $MAIL_DOMAIN.                TXT   "v=spf1 ip4:$IP_SHOWN ~all"
  $DKIM_SELECTOR._domainkey.$MAIL_DOMAIN.  TXT   "$DKIM_TXT"
  _dmarc.$MAIL_DOMAIN.         TXT   "v=DMARC1; p=none; rua=mailto:postmaster@$MAIL_DOMAIN"

And at your server/VPS provider (not your DNS provider):

  Reverse DNS (PTR) for $IP_SHOWN  ->  $DOMAIN

If $MAIL_DOMAIN already has an SPF record, add "ip4:$IP_SHOWN" to it
instead of creating a second one. See docs/DEPLOYMENT.md for details.
EOF_DNS
fi
