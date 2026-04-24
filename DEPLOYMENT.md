# BOZOapp — Production Deployment

Produkční setup pro Hetzner Cloud + Docker Compose + Caddy.

## 1. Server prerequisities

- Hetzner Cloud VM (min. CX22, ideálně CX32+ pro production load)
- Ubuntu 24.04 LTS
- Docker + docker compose plugin
- Firewall: 22 (SSH), 80/443 (HTTP/HTTPS) — DB a Redis jen lokálně
- DNS: `app.bozoapp.cz` → IP serveru

## 2. Secrets — NEGENERUJ DEFAULTNÍ HODNOTY

```bash
# SECRET_KEY (JWT signing) — min 32 znaků
python3 -c "import secrets; print(secrets.token_hex(32))"

# FERNET_KEY (encryption at rest — personal_id, totp_secret)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# DB passwords (bozoapp owner + bozoapp_app runtime)
openssl rand -base64 32
openssl rand -base64 32
```

**Ulož do password manageru** (1Password, BitWarden). Bez nich aplikace
nenastartuje (SECRET_KEY validator odmítne default/short).

## 3. Produkční .env

```dotenv
# App
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<vygenerováno v kroku 2>

# Database — DVA URL!
# Runtime jako bozoapp_app (least-privilege, non-owner)
DATABASE_URL=postgresql+asyncpg://bozoapp_app:<APP_PASSWORD>@db:5432/bozoapp_prod
# Migrace jako bozoapp (owner, DDL rights)
MIGRATION_DATABASE_URL=postgresql+asyncpg://bozoapp:<OWNER_PASSWORD>@db:5432/bozoapp_prod

# Redis
REDIS_URL=redis://redis:6379/0

# Encryption at rest
FERNET_KEY=<vygenerováno v kroku 2>

# CORS (odděleno čárkou pokud víc frontendů)
CORS_ORIGINS=https://app.bozoapp.cz

# SMTP (Postmark, SendGrid, Mailgun, Seznam, atd.)
SMTP_HOST=smtp.postmark.com
SMTP_PORT=587
SMTP_USER=<provider token>
SMTP_PASSWORD=<provider token>
SMTP_FROM=noreply@bozoapp.cz
SMTP_TLS=true

# Observability
SENTRY_DSN=https://...@sentry.io/<project>
```

## 4. DB setup (jednou při prvotním deployi)

Postgres v docker-compose startuje s `POSTGRES_USER=bozoapp` (owner) +
`POSTGRES_PASSWORD=<OWNER_PASSWORD>` + `POSTGRES_DB=bozoapp_prod`.

Po prvním startu DB, před migrací:

```bash
# 1) Vytvoř bozoapp_app role se svým secure passwordem.
#    ALEMBIC migrace 015 má DO block s default passwordem "bozoapp_app_dev_secret"
#    — ten v produkci nesmí zůstat. Nejdřív si vytvoř vlastní:
docker compose exec -T db psql -U bozoapp -d bozoapp_prod \
  -c "CREATE ROLE bozoapp_app WITH LOGIN PASSWORD '<APP_PASSWORD>';"

# 2) Pusť migrace
docker compose exec backend alembic upgrade head

# 3) Ověř že role má správná práva
docker compose exec -T db psql -U bozoapp -d bozoapp_prod \
  -c "\dp audit_log"  # bozoapp_app by měl mít {SELECT,INSERT,UPDATE,DELETE}
```

Alternativně: `scripts/create_prod_app_role.sql` — viz níže.

## 5. Backup strategie

### Denní pg_dump → Hetzner Object Storage

```bash
# V cronu (crontab -e):
0 2 * * * /opt/bozoapp/scripts/backup.sh >> /var/log/bozoapp_backup.log 2>&1
```

### WAL archiving (point-in-time recovery)

Pro produkční setup s SLA doporučujeme:
- Postgres `archive_mode = on`, `archive_command` → upload WAL segmentů do S3
- Příklad nástroje: [pgBackRest](https://pgbackrest.org/) nebo WAL-G
- Retence: 30 dní WAL + 7 denních fullů + 1 měsíční

Pro MVP stačí daily pg_dump. Upgrade na WAL archiving až bude traffic > 100 tenantů.

### Restore test — POVINNÝ měsíční drill

Backup bez ověřené restore procedury nefunguje. Minimálně 1× měsíčně:
```bash
# Stáhni poslední backup, obnov do staging DB, ověř integritu
./scripts/restore_test.sh 2026-04-23
```

## 6. Monitoring + alerting

- **Sentry** — errory (SENTRY_DSN nastaven). `send_default_pii=False`
  (neposílat zdravotní data!).
- **Grafana + Prometheus** (optional) — metrics z FastAPI přes
  `prometheus-fastapi-instrumentator`.
- **Uptime Kuma** / Pingdom — HTTP check na `/api/v1/health/ready`
  každou minutu. Alert na 5xx, timeout, certificate expiry.

## 7. Health check endpoints

- `GET /api/v1/health` — liveness. Vrací 200 OK pokud běží uvicorn.
  Nesmí dotýkat DB/Redis (každé 5s od LB).
- `GET /api/v1/health/ready` — readiness. Pinguje DB + Redis.
  503 pokud DB down. Použít v Kubernetes readinessProbe / LB health check.

## 8. CI/CD

GitHub Actions deployuje na push do `main`:
1. Backend CI projde (lint + mypy + migrations + pytest)
2. Frontend CI projde (typecheck + build)
3. Deploy job: SSH na server → `git pull` → `docker compose up --build -d`
4. Smoke test: `curl https://app.bozoapp.cz/api/v1/health/ready`

Migrace se spustí automaticky v deploy jobu přes
`docker compose exec backend alembic upgrade head`.

## 9. Role model a bootstrap platform admina

Od commitu 8 má aplikace 5 rolí:

- `admin` (platform-level, `is_platform_admin=True`) — SaaS operator
- `ozo` — full tenant access (odborně způsobilá osoba)
- `hr_manager` — full tenant access (zatím stejná práva jako ozo, budoucí split)
- `equipment_responsible` — employee + správa revizí (scope TBD)
- `employee` — self-access only

Flow: **platform admin vytvoří tenant + prvního OZO**, klient pak zve další
uživatele. V produkci se self-signup `/auth/register` vypne
(`ALLOW_SELF_SIGNUP=false`).

Prvního platform admina musíš vytvořit přes CLI (chicken-and-egg — admin
vytváří tenanty, ale jak vytvořit prvního admin?):

```bash
docker compose exec \
  -e ADMIN_EMAIL=admin@bozoapp.cz \
  -e ADMIN_PASSWORD='<secure-pwd-min-12-chars>' \
  backend \
  python -m app.commands.create_platform_admin --non-interactive
```

Skript vytvoří servisní tenant "BOZOapp Platform" a usera s `is_platform_admin=True`,
`role='admin'`. Heslo si admin může potom změnit přes standardní flow.

Dál admin používá `POST /api/v1/admin/tenants` pro každého nového klienta:
```json
{"tenant_name": "Klient s.r.o.", "ozo_email": "ozo@klient.cz"}
```
Klient-OZO dostane password-reset email a nastaví si heslo.

## 10. Čeklist před prvním klientem

- [ ] Vygenerovat SECRET_KEY, FERNET_KEY, DB passwordy, uložit do password manageru
- [ ] Nasadit postgres + redis + backend + frontend na Hetzner
- [ ] DNS + TLS cert (Caddy automatic)
- [ ] Spustit migrace (všech 19) včetně FORCE RLS
- [ ] Vytvořit bozoapp_app role se secure passwordem
- [ ] Nastavit CORS_ORIGINS
- [ ] ALLOW_SELF_SIGNUP=false v prod .env
- [ ] Nakonfigurovat SMTP (odeslat test email přes `/auth/forgot-password`)
- [ ] Sentry DSN aktivní, testovat fake error
- [ ] Nastavit denní backup cron + test restore
- [ ] GDPR export/delete endpointy protestovat end-to-end
- [ ] 2FA setup pro první OZO účet — povinné u přístupu ke zdravotním datům
- [ ] **Vytvořit platform admina přes `python -m app.commands.create_platform_admin`**
- [ ] **Přes admin dashboard / API vytvořit prvního klientského tenanta**
- [ ] Uptime monitoring na /health/ready

## 10. Security posture

Co máme v kódu:
- FORCE ROW LEVEL SECURITY na 17 tenantovaných tabulkách
- Least-privilege DB role (bozoapp_app bez DDL)
- Argon2id password hashing
- Refresh token rotation + family revocation (reuse detection)
- CSRF double-submit cookie
- Rate limiting + progressive delay
- TOTP 2FA s recovery codes
- Fernet encryption at rest pro personal_id
- Audit log (automatický CREATE/UPDATE/DELETE trace, partitioned by month)
- Structured logging s request_id + tenant_id + user_id kontextem
- Sentry s `send_default_pii=False`

Co má udělat operator:
- Rotace secretů min 1× ročně
- Brute-force monitoring (Fail2ban na SSH, interní přes rate limiter)
- DDoS ochrana přes Caddy / Cloudflare
- Penetrační test před prvním velkým klientem
