# Subdomain-based multi-tenancy

## Přehled

Každý tenant má svůj subdomain. Login + UI jsou brandované podle firmy.
DB zůstává sdílená (pool model), izolace přes RLS jako dosud.

| Subdomain | Účel |
|---|---|
| `strojirny-abc-s-r-o.localhost:3000` | Tenant Strojírny ABC |
| `pekarny-xyz-a-s.localhost:3000` | Tenant Pekárny XYZ |
| `stavebni-firma-delta.localhost:3000` | Tenant Stavební firma DELTA |
| `admin.localhost:3000` | Platform admin (admin@demo.cz) |
| `localhost:3000` | Root — fallback, generic login |

V produkci `.localhost` → `.digitalozo.cz`.

## Lokální dev

`*.localhost` se v Chrome / Firefox automaticky resolvuje na `127.0.0.1`
(RFC 6761). Žádný hosts file.

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.tasks.seed_demo
```

Pak v browseru:

- **OZO klasický login** (s emailem):
  `http://strojirny-abc-s-r-o.localhost:3000` → `ozo@demo.cz` / `demo1234`

- **Login po osobním čísle** (zaměstnanec bez emailu):
  `http://strojirny-abc-s-r-o.localhost:3000` → osobní číslo (např. `P1234`)
  z karty zaměstnance „Tomáš Dvořák" / `demo1234`

- **SMS login**: tab „SMS kód" → email/osobní číslo → kód `111111` (dev mock)

- **Platform admin**:
  `http://admin.localhost:3000` → `admin@demo.cz` / `demo1234`

## Login flow

Backend přijímá `identifier` (email | personal_number | username) +
volitelný `tenant_slug`. Tenant se rezolví v tomto pořadí:

1. **Body field `tenant_slug`** (z formuláře, pokud klient pošle)
2. **HTTP header `X-Tenant-Slug`** (FE wrapper ho posílá automaticky
   z `window.location.hostname`)
3. **Host header subdoména** (extrakce backend middlewarem)

Identifier je rozeznán podle obsahu:
- `'@' v string` → email (search per-tenant pokud je tenant resolved, jinak globálně)
- `tenant_id != None && obsahuje jen číslice/písmena` → `Employee.personal_number` v rámci tenantu
- fallback → `User.username` (platform admin)

## Cookie scope

`settings.cookie_domain`:
- **Prod** `.digitalozo.cz` → cookie sdílený mezi `*.digitalozo.cz` →
  OZO multi-client switcher prostě redirektne na druhý subdomain.
- **Dev** `""` (prázdný) → cookie per-host. Switcher fallback na
  `/auth/select-tenant` + reload na stejném subdomain. Multi-tenant
  testování v dev → každý subdomain má vlastní login.

Pro dev cross-subdomain SSO zkus nastavit `COOKIE_DOMAIN=".localhost"`
v docker-compose.yml (Chrome to akceptuje, Safari historicky problém).

## Architektura

```
Browser (strojirny-abc.localhost:3000)
   ↓
Next.js dev server :3000 (frontend container)
   ↓ Host: strojirny-abc.localhost:3000
   ↓ X-Tenant-Slug: strojirny-abc-s-r-o (header forwarded by middleware.ts)
   ↓
FastAPI :8000 (backend container)
   ↓
TenantSubdomainMiddleware
   ↓ request.state.tenant_from_subdomain = UUID(...)
   ↓
LoginEndpoint → resolve identifier within tenant_id → JWT
```

## Produkční checklist

- [ ] DNS: `*.digitalozo.cz` A/AAAA → server
- [ ] Caddy: wildcard SSL (Let's Encrypt DNS-01 challenge)
- [ ] `BASE_DOMAIN=.digitalozo.cz`, `COOKIE_DOMAIN=.digitalozo.cz`
- [ ] `APP_URL_SCHEME=https`, `APP_URL_PORT=""`
- [ ] CORS: regex `https://([a-z0-9-]+\.)?digitalozo\.cz` (už hotové)
- [ ] Test: `klient1.digitalozo.cz` login + switcher → `klient2.digitalozo.cz`

## Rollback

Vypnout subdomain model = nastavit `BASE_DOMAIN=""` (středdomain
middleware nic nedělá, login funguje jako dřív přes email + global
search).
