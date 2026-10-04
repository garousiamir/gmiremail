# Deploying gmiremail on your own server

`deploy/install.sh` sets up everything on **one server**. After it runs, the dashboard is on your hostname over HTTPS, and email goes out **directly from this server** to your recipients' mail servers (Gmail, Outlook and so on), signed with DKIM.

```
 browser ──HTTPS──▶ nginx (Let's Encrypt) ──▶ gunicorn: web app + dashboard ──▶ PostgreSQL
                                                                               ▲
                                   gmiremail-worker (queue, automations, stats)┘
                                          │ SMTP on 127.0.0.1:25
                                          ▼
                       Postfix (send-only) + OpenDKIM ──port 25──▶ recipients' mail servers
```

| Component | What it is |
|---|---|
| `gmiremail-web` | gunicorn serving the API and dashboard on 127.0.0.1:8000 |
| `gmiremail-worker` | The only process running background jobs: sending, automations, analytics, cleanup |
| PostgreSQL | The database, with a daily backup to `/var/backups/gmiremail` (14 days kept) |
| nginx + certbot | HTTPS on your hostname. The certificate renews automatically |
| Postfix + OpenDKIM | Send-only mail server on localhost that DKIM-signs every message. It is not reachable from outside |

## Requirements

- A VPS running **Ubuntu 22.04/24.04 or Debian 12**, with root access. 1 GB of RAM is enough to start.
- A hostname for the dashboard, e.g. `mail.example.com`, plus the domain you send from, e.g. `example.com` (it can be the same name).
- **Outbound port 25 open.** Many providers (DigitalOcean, AWS, GCP, Azure, and new Hetzner/Vultr accounts) block it until you ask them to unblock it. The installer checks for this. If you can't get it opened, see [Using an external SMTP service](#using-an-external-smtp-service-instead).
- The ability to set **reverse DNS (PTR)** for the server's IP. This is done in your VPS provider's panel.

## 1. Point your hostname at the server

At your DNS provider, create an `A` record such as `mail.example.com` pointing to the server's IPv4 address. Wait until `dig +short mail.example.com` returns that IP, because the HTTPS certificate request needs it.

## 2. Install

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/garousiamir/gmiremail /opt/gmiremail
cd /opt/gmiremail
sudo deploy/install.sh --domain mail.example.com --email you@example.com --mail-domain example.com
```

| Option | Meaning |
|---|---|
| `--domain` | Hostname for the dashboard, the tracking links, and the HELO name of the mail server |
| `--email` | Your address for Let's Encrypt expiry notices |
| `--mail-domain` | The domain in your From address (`news@example.com` → `example.com`). Defaults to `--domain` |
| `--no-postfix` | Skip the local mail server and send through an external SMTP service |
| `--skip-certbot` | Don't request a certificate yet. Re-run without it later |

The script can be run again safely (for example after fixing DNS). It keeps the existing secrets, database, DKIM keys and certificates.

At the end it prints the DNS records for step 3.

## 3. DNS records for email delivery

Without these, mail providers will put your messages in spam or reject them. The installer prints the exact values. They look like this:

| Record | Type | Value | Why |
|---|---|---|---|
| `example.com` | TXT | `v=spf1 ip4:203.0.113.10 ~all` | **SPF:** allows this server to send for your domain |
| `mail._domainkey.example.com` | TXT | `v=DKIM1; h=sha256; k=rsa; p=MIIB…` | **DKIM:** public key matching the signature on each message |
| `_dmarc.example.com` | TXT | `v=DMARC1; p=none; rua=mailto:postmaster@example.com` | **DMARC:** required by Gmail and Yahoo for bulk senders |
| PTR for `203.0.113.10` | (set at your VPS provider) | `mail.example.com` | **Reverse DNS:** without it, many providers reject mail outright |

- **Existing SPF record:** if your domain already has one (for example from Google Workspace), don't add a second. Add `ip4:<server IP>` to the existing one, e.g. `v=spf1 ip4:203.0.113.10 include:_spf.google.com ~all`.
- **Long DKIM key:** some DNS panels can't take the long DKIM value in one piece. Paste it as several quoted strings in the same record.

Check the records with `dig +short TXT mail._domainkey.example.com` and `dig +short -x 203.0.113.10`.

## 4. First login and a test send

1. Open `https://mail.example.com/` and create your account.
   - Use a **sender email on your mail domain** (e.g. `news@example.com`).
   - Leave the SMTP fields empty. New accounts default to the local Postfix.
2. In **Settings → SMTP server**, click **Test connection**.
3. Create a template, add yourself as a subscriber, and send a campaign.
4. In Gmail, open the message, choose **⋮ → Show original**, and check for `SPF: PASS`, `DKIM: PASS` and `DMARC: PASS`.
5. Optionally, send a campaign to the address that [mail-tester.com](https://www.mail-tester.com) gives you for a deliverability score.

## Warming up a new server

A new IP address has no sending reputation. Bulk mail from it on day one goes to spam, and the IP can end up on blocklists. The installer starts with low limits in `/etc/gmiremail/gmiremail.env`:

```
DAILY_EMAIL_LIMIT=500
MAX_EMAILS_PER_MINUTE=20
```

Raise them over 2–4 weeks, e.g. 500 → 1,000 → 2,500 → 5,000 → … a day. Send to your most engaged subscribers first.

The daily limit also exists per business, under **Settings → Daily sending limit**. The lower of the two applies to new accounts.

After editing the env file, run `sudo systemctl restart gmiremail-web gmiremail-worker`.

Mail over a limit isn't lost. It stays queued and goes out once the limit allows.

## Replies and bounces

This Postfix is **send-only**: it doesn't receive mail. Replies and late bounce messages go to your **From address**, so use an address you actually read. A common setup is a domain whose mailboxes are hosted elsewhere, like Google Workspace or Fastmail, with this server added to its SPF record as shown above.

The platform learns about bounces that the receiving server reports during delivery. A remote server that accepts a message and only bounces it later sends that bounce to your From mailbox. You then need to mark the subscriber **bounced** yourself, in **Subscribers → status**.

## Using an external SMTP service instead

If port 25 stays blocked, or you'd rather use a provider such as SendGrid, Mailgun, Amazon SES or Gmail:

```bash
sudo deploy/install.sh --domain mail.example.com --email you@example.com --no-postfix
```

Then enter the provider's SMTP host, port 587, username and password under **Settings → SMTP server**. Set up the SPF and DKIM records that the provider asks for, instead of the ones above.

## Sending for more than one domain

Each business in the dashboard can send from its own domain. To give another domain DKIM signing on this server, run:

```bash
sudo deploy/add-dkim-domain.sh otherbrand.com
```

The script prints the DKIM record to publish. Add SPF and DMARC records for that domain the same way as above.

## Day-to-day operations

| Task | Command |
|---|---|
| Live logs | `sudo journalctl -u gmiremail-web -u gmiremail-worker -f` |
| Restart | `sudo systemctl restart gmiremail-web gmiremail-worker` |
| Update to the latest code | `cd /opt/gmiremail && sudo git pull && sudo deploy/update.sh` |
| Settings and secrets | `/etc/gmiremail/gmiremail.env` (restart after changes) |
| Postfix queue / delivery log | `mailq` · `sudo journalctl -u postfix -f` |
| Backups | `/var/backups/gmiremail/gmiremail-YYYY-MM-DD.dump` (daily, kept 14 days) |
| Restore a backup | `sudo systemctl stop gmiremail-web gmiremail-worker && sudo runuser -u postgres -- pg_restore --clean -d gmiremail /var/backups/gmiremail/<file>.dump && sudo systemctl start gmiremail-web gmiremail-worker` |
| Certificate renewal | Automatic (certbot timer). Check with `sudo certbot renew --dry-run` |

**Firewall:** only SSH and web traffic need to be open, so port 25 does *not* need to accept inbound connections:

```bash
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

Copy the backups off the server now and then, e.g. with `rsync` to another machine.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Certificate request failed | The DNS `A` record doesn't point to this server yet, or port 80 is blocked. Fix it and re-run `install.sh` |
| Emails stay *queued* | Check `journalctl -u gmiremail-worker`. The daily or per-minute limit may be reached, or the campaign is paused |
| Emails *sent* in the app but never arrive | Check `sudo journalctl -u postfix`. `Connection timed out` on port 25 means your provider blocks it. `550 … PTR` or `… SPF` means step 3 isn't finished |
| Everything lands in spam | Finish SPF/DKIM/DMARC/PTR, warm up slowly, and send only to people who opted in |
| Dashboard shows 502 | `sudo systemctl status gmiremail-web` and `journalctl -u gmiremail-web` |
