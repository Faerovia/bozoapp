---
title: "DigitalOZO — Vývojářská dokumentace"
subtitle: "Vertikální SaaS pro BOZP a PO na český trh"
author: "Lukáš Voráček (zakladatel, OZO) + CTO"
date: "Verze 1.0 · Duben 2026"
---

# 1. Úvod

## 1.1 Co projekt řeší

DigitalOZO je vertikální SaaS pro **BOZP** (bezpečnost a ochrana zdraví při práci) a **PO** (požární ochrana) zaměřený na český trh. Cílem je digitalizovat agendu odborně způsobilých osob (OZO) a HR managerů malých a středních podniků: registr rizik, hodnocení rizikových faktorů, lékařské prohlídky, revize, OOPP, školení, pracovní úrazy, provozní deníky a generování legislativně povinných dokumentů.

Aplikace je multi-tenant (1 instance, N zákazníků), s důrazem na auditovatelnost, izolaci dat a soulad s českou legislativou (Zákoník práce §102, NV 361/2007, vyhláška 79/2013, NV 390/2021, NV 378/2001, GDPR, eIDAS).

## 1.2 Cílová audience této dokumentace

Dokument je psán pro **nové vývojáře** přicházející do projektu a pro **CTO**, který potřebuje rychle pochopit architekturu, datový model a klíčové invarianty. Není to ani onboarding pro klienty, ani audit dokumentace. Cílem je odpovědět na otázky:

- Kde je co?
- Jak jsou na sebe moduly napojené?
- Jaké jsou hard rules, které nesmím porušit?
- Jak přidám novou feature, abych zachoval konzistenci?

## 1.3 Technický stack

**Backend:**

- Python 3.12, FastAPI (async)
- SQLAlchemy 2.x async + Alembic migrace
- PostgreSQL 16 + pgvector (RLS, JSONB, GENERATED columns)
- Redis 7 (rate limiting, sessions, cache)
- PyJWT + Argon2id (auth)
- fpdf2 (PDF export)
- Anthropic Claude API (AI generátor dokumentů)
- pytest + pytest-asyncio (real DB testing)
- ruff + mypy strict (lint, types)

**Frontend:**

- Next.js 14/15 App Router, TypeScript
- TanStack Query v5 (server state)
- React Hook Form + Zod (formuláře)
- Tailwind CSS v3 + class-variance-authority (design system)
- Lucide ikon
- ESLint, Next.js TS strict

**Infrastruktura:**

- Hetzner Cloud (EU/DE) — povinný region kvůli GDPR
- Docker Compose (dev) + Docker Swarm/Kubernetes (prod)
- Caddy reverse proxy (TLS termination, subdomain routing)
- Hetzner Object Storage (S3-compatible) pro nahrávané soubory
- GitHub Actions CI/CD

**Klíčové neměnné rozhodnutí:**

- **Pool model multi-tenancy** s PostgreSQL Row-Level Security (RLS) — žádné per-tenant databáze
- **Subdomain-based tenant routing** (`{slug}.digitalozo.cz`)
- **JWT + httpOnly cookies + Bearer dual auth** — Bearer má prioritu (testovatelnost, API klienti)
- **Real DB v testech** — žádné mocky databáze (RLS politiky se nedají mockovat)
- **OZO multi-client** — jeden uživatel může mít přístup k více tenantům přes `UserTenantMembership`

## 1.4 Repozitář

Monorepo `bozoapp/` na GitHubu (privátní). Struktura:

```
bozoapp/
├── backend/
│   ├── app/
│   │   ├── api/v1/           # routery (jeden soubor = jeden modul)
│   │   ├── models/           # SQLAlchemy modely
│   │   ├── schemas/          # Pydantic v2 schémata
│   │   ├── services/         # business logika
│   │   └── core/             # db, dependencies, security, permissions
│   ├── migrations/versions/  # Alembic 001 → 066+
│   ├── tests/                # pytest + real DB
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/(dashboard)/  # stránky modulů
│   │   ├── app/(auth)/       # login, register, reset-password
│   │   ├── components/ui/    # Button, Card, Dialog, Input, Label
│   │   ├── components/layout/# Header, Sidebar
│   │   ├── lib/              # api wrapper, query-keys, query-client
│   │   └── types/api.ts      # všechny TS typy z API
│   └── package.json
├── docker-compose.yml
├── DEPLOYMENT.md
└── docs/
```

\newpage

# 2. Architektura

## 2.1 High-level pohled

```
                       Internet
                          │
                          ▼
           ┌─────────────────────────────┐
           │  Caddy (TLS, subdomain LB)  │
           └──────────┬──────────────────┘
                      │
       ┌──────────────┴──────────────┐
       ▼                             ▼
  Next.js (SSR)                 FastAPI (uvicorn)
  /app/(dashboard)              /api/v1/*
       │                             │
       │                             ▼
       │                       ┌──────────┐
       └─── /api proxy ───────►│ Postgres │ (RLS, pgvector)
                               │  Redis   │ (rate limit, cache)
                               │ Hetzner  │ (S3-compat object storage)
                               └──────────┘
```

## 2.2 Monorepo + mikroslužby?

Záměrně **monorepo**, ale logicky 2 deploy artefakty: backend (Python) a frontend (Node). Žádné mikroslužby — projekt je dostatečně malý, side-projekt s ~15h/týdně dvou lidí. Mikroslužby by zbytečně zvyšovaly operační náklady.

## 2.3 Multi-tenant model

**Pool model** — jedna PostgreSQL databáze, všechna data všech tenantů v jedněch tabulkách, izolace přes:

1. **`tenant_id` na každé tabulce** (FK na `tenants.id`, `ON DELETE CASCADE`)
2. **PostgreSQL RLS** policy `tenant_isolation` na každé tabulce
3. **Session-local context** `app.current_tenant_id` setovaný v každém requestu
4. **Subdomain routing** — každý tenant má svůj slug (`firma1.digitalozo.cz`)

Trade-off:

- Pro: levné (1 DB), jednoduchá migrace, snadné cross-tenant query pro platform admina, kompaktní backupy
- Proti: jeden bug v RLS = potenciální data breach napříč tenanty (proto je to testované, viz Sekce 9)

## 2.4 Hosting a deployment

**Dev:** Docker Compose lokálně. PostgreSQL 16 + Redis 7 + backend (uvicorn --reload) + frontend (next dev). Subdomény přes `firma1.localhost` (Chrome akceptuje wildcard `*.localhost` jako loopback).

**Prod (plánované):** Hetzner Cloud Helsinki/Falkenstein, Docker Compose s Caddy reverse proxy. TLS přes ACME (Let's Encrypt). Storage: Hetzner Object Storage. Backupy: postgres-backup-s3 + S3 lifecycle 30 dní.

\newpage

# 3. Bezpečnost a autentizace

## 3.1 JWT model

**Access token:**

- Lifetime: 15 minut (env `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Algoritmus: HS256
- Payload: `{ sub: user_id, tenant_id, role, type: "access", exp }`
- Storage: httpOnly cookie (`access_token`) + Bearer header
- **Bearer má prioritu** — `_extract_token()` v `core/dependencies.py` čte nejdřív `Authorization: Bearer ...`, až pak cookie. Důvod: API klienti a testy nesmí být zmateny stale cookies.

**Refresh token:**

- Lifetime: 7 dní (env `REFRESH_TOKEN_EXPIRE_DAYS`)
- Payload: `{ sub, tenant_id, type: "refresh", exp, jti, family_id }`
- Uloženo v `refresh_tokens` tabulce s `used: bool`, `revoked_at`, `revoked_reason`
- Storage: httpOnly cookie scope `path=/api/v1/auth/refresh` (minimalizuje exposure)

## 3.2 Refresh token rotation s reuse detection

Při každém `/auth/refresh` se starý JTI označí `used=true` a vydá se nový s **stejným `family_id`**. Pokud klient pošle už použitý token (replay attack / token theft), systém:

1. Detekuje `used=true` v DB
2. Revokuje **celou rodinu** (všechny tokeny s daným `family_id`)
3. Set `revoked_reason="reuse_detected"`
4. Vrátí 401, vyžadovat plný re-login

Implementace v `services/refresh_tokens.py`. Test: `tests/test_refresh_rotation.py::test_refresh_reuse_triggers_family_revocation`.

## 3.3 Password hashing

Argon2id přes Passlib (`passlib[argon2]`). Default parameters (memory_cost 64MB, time_cost 3, parallelism 4). Verifikace přes `verify_password(plain, hashed)`. Migrace starších hesel (kdyby přišly): `deprecated="auto"`.

## 3.4 TOTP 2FA

Volitelné per-uživatel. `User.totp_secret` je **Fernet-encrypted** base32 string (klíč v env `FERNET_KEY`). Workflow:

1. POST `/totp/setup` → backend vygeneruje secret, vrátí QR jako data URI + plaintext secret (jednorázově)
2. User naskenuje QR v Google Authenticatoru
3. POST `/totp/enable` s 6místným kódem → backend ověří a uloží encrypted secret
4. Při dalším loginu: backend vrátí `403 { totp_required: true }` → frontend ukáže OTP pole → POST `/auth/login` s `totp_code`

**Recovery codes:** 8 jednorázových SHA-256 hashů uložených v `recovery_codes` tabulce. Při ztrátě telefonu lze použít.

## 3.5 SMS OTP login (alternativa hesla)

Pro zaměstnance, kteří nepamatují heslo. Workflow:

1. POST `/auth/sms/request` s `personal_number` → backend pošle 6místný kód SMS branou (Twilio/SMS.cz/...)
2. POST `/auth/sms/verify` s `personal_number + code` → vrátí JWT tokeny
3. Kód: 6 číslic, 5 minut TTL, 3 pokusy, throttle per personal_number

Tabulka `login_sms_otp_codes`. Backend musí mít konfigurovaný SMS provider (env `SMS_PROVIDER`).

## 3.6 Subdomain login & cross-tenant ochrana

Subdomain rezolver (Sekce 4) vyplní `request.state.tenant_from_subdomain`. Login endpoint `/auth/login`:

1. Uživatel pošle `{ identifier, password }` — identifier může být email (globálně unikátní), `personal_number` (per-tenant unikátní), nebo username (globálně unikátní).
2. Backend hledá usera v daném tenantě (z subdomény).
3. Při úspěchu vydá JWT s `tenant_id` z URL — **nezdaří se přihlásit do jiného tenantu, i kdyby uživatel měl tam membership**, protože `tenant_id` v JWT musí matchovat subdoménu.

Cross-tenant access je možný jen pro:

- **OZO multi-client** přes ClientSwitcher (frontend mění subdomenu, dělá nový login flow s SMS OTP)
- **Platform admin** (flag `is_platform_admin` na User, RLS bypass policy)

`get_current_user` v `core/dependencies.py` ověří, že:

- JWT je validní, nestaří, není revoked
- User existuje, je aktivní
- User má `UserTenantMembership` s `tenant_id` z JWT (kromě platform admina)

Funkce `assert_in_tenant(db, model, fk_id, tenant_id)` v `core/validation.py` se volá na všech FK referencích v `services/` — chrání před tím, aby si někdo z tenant A namapoval `employee_id` z tenantu B.

## 3.7 CSRF (double-submit cookie)

Pro requesty se **cookie auth** (browser, není Bearer). Middleware `core/csrf.py`:

1. Při GET requestech na chráněné endpointy generuje `csrf_token` cookie (non-httpOnly, čitelná z JS)
2. Při POST/PUT/PATCH/DELETE musí klient poslat `X-CSRF-Token: <hodnota cookie>`
3. Mismatch → 403

**Bearer auth je výjimkou** — Bearer token v hlavičce nelze automaticky poslat napříč doménami (CORS), takže CSRF je redundantní. Test: `test_csrf.py::test_bearer_bypass`.

Exempt paths: `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/sms/*` — uživatel ještě nemá CSRF cookie nastavenou.

## 3.8 Rate limiting

Dvě vrstvy:

**slowapi (per-endpoint):**

- `/auth/register`: 5 / hodina / IP
- `/auth/login`: 20 / minuta / IP
- `/auth/sms/request`: 3 / hodina / IP
- Ostatní: bez explicitního limitu

**Progressive delay (login fail):** Redis counter `login_fail:{email_lower}` s TTL 15 minut. Mapping fail count → delay [s]:

| Fails | Delay |
|------:|------:|
|  0–1  | 0     |
|  2    | 0.5   |
|  3    | 1     |
|  4    | 2     |
|  5    | 4     |
|  6    | 8     |
|  7    | 15    |
|  8    | 30    |
|  9+   | 60 (block) |

V testech (`ENVIRONMENT=test`) je rate limit zakázán. Fail-open: pokud Redis spadne, backend degraduje bez logování (přístupnost > security pro tento konkrétní vector).

## 3.9 Audit log (append-only)

Tabulka `audit_log` zachycuje všechny INSERT/UPDATE/DELETE napříč business tabulkami. Implementace:

- SQLAlchemy event listener `before_flush` v `core/audit.py`
- DB triggery blokují UPDATE/DELETE na `audit_log` samotné
- Diff `old_values` / `new_values` jako JSONB
- Skip columns: `hashed_password`, `created_at`, `updated_at` (technické bez business smyslu)
- Tenant_id se automaticky přečte z `instance.tenant_id`

Request kontext (IP, user_agent, user_id, tenant_id) se ukládá přes ContextVar `_request_ctx`, kterou plní `RequestContextMiddleware`.

\newpage

# 4. Multi-tenant izolace

## 4.1 Subdomain rezolver

`core/tenant_subdomain.py::TenantSubdomainMiddleware`:

1. Extrahuje hostname z `Host` headeru (případně `X-Tenant-Slug` jako fallback za Next.js proxy)
2. Vyparsuje subdoménu (`firma1.digitalozo.cz` → `firma1`)
3. Lookup v `tenants` tabulce přes `slug` (LRU cache 60s)
4. Uloží do `request.state`:
   - `tenant_from_subdomain`: UUID nebo None
   - `tenant_slug`: string
   - `tenant_name`: pro branded login UI
5. Reserved subdomains (`admin`, `www`, `api`, `app`, `static`, `cdn`, `mail`, `ftp`): `tenant_from_subdomain = None`, `is_admin_subdomain = True`

Cache invalidation: když se změní slug (rename tenanta), volat `invalidate_cache(slug)` z services/tenants.

## 4.2 RLS context per request

`core/database.py::get_db()` yield-uje AsyncSession. V dependencies pipeline:

1. `TenantSubdomainMiddleware` → tenant z URL
2. `get_current_user(db, request)` → ověří JWT, dostane user
3. **V `get_current_user`** se setuje session-local kontext:
   ```sql
   SET LOCAL app.current_tenant_id = '<uuid>';
   ```
4. Pokud user `is_platform_admin = true`, navíc:
   ```sql
   SET LOCAL app.is_platform_admin = 'true';
   ```

RLS politika na každé tabulce (vytváří se v migraci):

```sql
CREATE POLICY tenant_isolation ON risks
  FOR ALL TO bozoapp_app
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid
         OR current_setting('app.is_platform_admin', true) = 'true');
```

Aplikační kód (services) **musí** stejně filtrovat `tenant_id`, RLS je defense-in-depth, ne jediná ochrana.

## 4.3 Database role separation

Dvě DB role:

- `bozoapp` (owner) — DDL, používaný pouze Alembic migracemi (`MIGRATION_DATABASE_URL`)
- `bozoapp_app` (least-privilege) — runtime aplikace (`DATABASE_URL`), nemůže `BYPASSRLS`

Tím je RLS nezneužitelná i z aplikačního kódu (kromě `SET LOCAL` rolemi).

## 4.4 OZO multi-client

OZO konzultant často slouží více klientům. Tabulka `user_tenant_memberships` (M:N):

| Sloupec | Typ | Význam |
|---------|-----|--------|
| user_id | UUID FK | OZO uživatel |
| tenant_id | UUID FK | klient |
| role | varchar | ozo / hr_manager / equipment_responsible / lead_worker / employee |
| is_default | bool | default kontext při loginu |

Frontend `ClientSwitcher` v Sidebaru:

1. Načte memberships přes `/auth/me`
2. Při kliknutí přesměruje na `https://{cilovy-slug}.digitalozo.cz/login` s URL hint
3. Tam proběhne nový login flow (SMS OTP nebo password) → JWT s novým `tenant_id`

\newpage

# 5. Datový model

Aplikace má cca 30 SQLAlchemy modelů v `backend/app/models/`. Všechny dědí z `Base` a obvykle z `TimestampMixin` (`created_at`, `updated_at`). Téměř všechny mají `tenant_id` UUID FK na `tenants.id` (`ON DELETE CASCADE`).

## 5.1 Tenanty a uživatelé

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `tenants` | `tenant.py` | Multi-tenant root entity. Slug (subdomain), fakturace, onboarding stav. |
| `users` | `user.py` | Autentizace. `email` NULLABLE (od migrace 063 — zaměstnanci se logují přes `personal_number`). TOTP secret encrypted. |
| `user_tenant_memberships` | `membership.py` | M:N OZO multi-client. `role` per tenant, `is_default`. |
| `refresh_tokens` | `refresh_token.py` | Token rotation s `family_id` reuse detection. |
| `audit_log` | `audit_log.py` | Append-only trail. DB triggery blokují UPDATE/DELETE. JSONB old/new values. |
| `recovery_codes` | `recovery_code.py` | 8× SHA-256 backup kódů pro 2FA. |
| `password_reset_tokens` | `password_reset_token.py` | One-time SHA-256 reset linky. |
| `login_sms_otp_codes` | `login_otp.py` | 6místný OTP, 5min TTL. |

## 5.2 Pracoviště (hierarchie)

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `plants` | `workplace.py` | Provozovna (areál, závod). |
| `workplaces` | `workplace.py` | Pracoviště v rámci provozovny (Plant). |
| `job_positions` | `job_position.py` | Pracovní pozice. `work_category` (1/2/2R/3/4 dle NV 361/2007). 1:1 s `RiskFactorAssessment`. |

Hierarchie: `Plant → Workplace → JobPosition`.

## 5.3 Zaměstnanci

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `employees` | `employee.py` | HR data. `personal_id` (rodné číslo) je `EncryptedString` (Fernet) — GDPR Čl. 9. `employment_type`: HPP / DPP / DPČ / external / brigade. Vazba na `users` (volitelná). |

## 5.4 Hodnocení rizik (ČSN ISO 45001)

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `risk_assessments` | `risk_assessment.py` | Strukturované hodnocení nebezpečí. 4 scope_type: workplace / position / plant / activity. P×S 5×5 matice. `initial_score` a `residual_score` jsou **GENERATED ALWAYS** v PG (SQLAlchemy `Computed()`). |
| `risk_measures` | `risk_assessment.py` | Opatření per riziko. Hierarchie ISO 45001: elimination → substitution → engineering → administrative → ppe. Vazba na `position_oopp_items` (PPE measure → auto výdej OOPP) a `trainings` (administrative → assignment). |
| `risk_assessment_revisions` | `risk_assessment.py` | Audit trail. JSONB `snapshot` při každé změně RA. |
| `risk_factor_assessments` | `risk_factor_assessment.py` | NV 361/2007 kategorizace prací. 13 faktorů (silika, vibrace, hluk, záření...) × 5 ratingů (1/2/2R/3/4). `category_proposed` = MAX(13 faktorů). |
| `risks` | `risk.py` | Legacy jednoduchý registr (zachován pro existující data). |

**Status workflow** RA: `draft → open → in_progress → mitigated → accepted → archived`. Když RA přejde do `accepted`, automaticky se uzavřou navázané `accident_action_items` (Sekce 7).

**Hazard categories** (od dubna 2026): 21 kategorií dle praxe OZO — `slip_trip`, `splash_flying_particles`, `hot_surfaces`, `manual_handling`, `chemical_splash`, `dust`, `gas`, `falling_object`, `pressure_release`, `working_at_height`, `cutting`, `low_clearance`, `tool_drop`, `electrical`, `forklift`, `machine_entanglement`, `noise`, `fire_explosion`, `confined_space`, `crane`, `other`.

## 5.5 Školení

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `trainings` | `training.py` | Šablona školení. `training_type`: BOZP / PO / first_aid / ... `requires_qes` (eIDAS ZES podpis). JSONB pole `test_questions`. Approval workflow (status `pending_approval` pokud non-OZO autor). |
| `training_assignments` | `training.py` | Přiřazení zaměstnanci. Deadline default 7 dní. `valid_until` (= `completed_at + valid_months`). Dual signature: `signature_canvas_b64` (legacy) + `universal_signature_id`. |
| `training_attempts` | `training.py` | Pokusy o test. `score_pct`, `passed`. |
| `training_signature_otps` | `training_signature_otp.py` | 6místný OTP pro ZES podpis školení. |

## 5.6 Lékařské prohlídky

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `medical_exams` | `medical_exam.py` | Vstupní / periodická / výstupní / mimořádná / odborná. `result`: zpusobily / zpusobily_omezeni / nezpusobily / pozbyl_zpusobilosti. `validity_status` derivovaný (valid / expiring_soon / expired / no_expiry). |

Periodicita podle vyhlášky 79/2013 Sb.:

| Kategorie | < 50 let | ≥ 50 let |
|----------:|---------:|---------:|
| 1         | 6 let    | 4 roky   |
| 2         | 4 roky   | 2 roky   |
| 2R        | 2 roky   | 2 roky   |
| 3         | 2 roky   | 2 roky   |
| 4         | 1 rok    | 1 rok    |

Implementace v `services/medical_exams.py::_resolve_periodic_months()`. Auto-generace prohlídek běží jako background job + při změně `work_category` na pozici (`reconcile_exams_for_employees_on_position`).

## 5.7 Pracovní úrazy

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `accident_reports` | `accident_report.py` | Záznam úrazu (formulář SÚIP). Status: draft / final / archived. `signature_required` (False pokud externí účastník). `required_signer_employee_ids` (pole UUID, kdo musí podepsat). |
| `accident_action_items` | `accident_action.py` | Akční plán. Default item "Revize a případná změna rizik" se vytvoří **při create úrazu** (i v draft fázi) a `related_risk_assessment_id` ukazuje na placeholder RA. |
| `accident_photos` | `accident_action.py` | Max 2 fotky per úraz. |

**Klíčový invariant** (od dubna 2026): úraz nesmí existovat bez default `accident_action_item` napojeného na `RiskAssessment`. Pokud `ensure_default_item()` selže, transakce se rollbackne (žádný silent except).

## 5.8 OOPP (NV 390/2021)

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `position_risk_grids` | `oopp.py` | Matrix 14 body parts × 26 risk columns (JSONB `{body_part: [risk_cols]}`). |
| `position_oopp_items` | `oopp.py` | OOPP katalog per pozice (helma, rukavice, ...). |
| `employee_oopp_issues` | `oopp.py` | Výdeje zaměstnancům. Universal signature pro digital receipt. |

## 5.9 Provozní deníky a revize

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `operating_log_devices` | `operating_log.py` | Zařízení s denním deníkem (VZV, kotelna, tlakové nádoby...). QR token pro tisk. |
| `operating_log_entries` | `operating_log.py` | Zápisy do deníku. `capable_items: yes/no/conditional`. |
| `revisions` | `revision.py` | Vyhrazená zařízení dle NV 378/2001 (elektro, plyn, kotle, výtahy). Auto-request 30 dní před `next_revision_at`. |
| `revision_records` | `revision.py` | Jednotlivé revize. PDF/foto protokolu. |
| `employee_plant_responsibilities` | `revision.py` | M:N — zaměstnanec odpovídá za revize provozovny. |
| `periodic_checks` | `periodic_check.py` | Sanační sady (vyhl. 432/2003), záchytné vany (NV 11/2002), lékárničky. |

## 5.10 Dokumenty

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `document_folders` | `document_folder.py` | Hierarchie dokumentů (self-FK). Code formát `000.001.005`. |
| `generated_documents` | `generated_document.py` | AI-generované (Claude API) nebo importované markdown/PDF. |

## 5.11 Digitální podpisy

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `signatures` | `signature.py` | Universal signature infrastructure. **Hash chain** (`prev_hash → chain_hash`) pro tamper-evidence. RFC 3161 TSA kotvy přes externí TSA (FreeTSA v MVP, PostSignum/I.CA před live). |
| `signature_anchors` | `signature.py` | Denní TSA kotvy. Každý den se hash chain "zakotví" do externí TSA → external proof nezměnitelnosti. |
| `sms_otp_codes` | `signature.py` | 6místný OTP pro podpis. |

## 5.12 Platform

| Tabulka | Soubor | Účel |
|---------|--------|------|
| `platform_settings` | `platform_setting.py` | Globální config (žádný RLS). Risk thresholds, exam rules, invoice settings. |
| `invoices` | `invoice.py` | Fakturace. `issuer_snapshot` + `recipient_snapshot` JSONB pro GDPR (smazání tenantu nesmí korumpovat historickou fakturu). |
| `invoice_counters` | `invoice.py` | Atomic counter per rok pro číslo faktury. |

\newpage

# 6. Backend — struktura a business logika

## 6.1 Adresářová struktura

```
backend/app/
├── main.py                  # FastAPI app, registrace routerů, middleware
├── core/
│   ├── database.py          # async engine, get_db, RLS context
│   ├── security.py          # JWT, password hashing
│   ├── dependencies.py      # get_current_user, role guards
│   ├── permissions.py       # require_role()
│   ├── tenant_subdomain.py  # multi-tenant middleware
│   ├── csrf.py              # CSRF middleware
│   ├── audit.py             # audit log SQLAlchemy listener
│   ├── observability.py     # structured logging, Sentry
│   ├── rate_limit.py        # slowapi setup
│   ├── validation.py        # assert_in_tenant
│   └── storage.py           # file upload (S3-compat)
├── models/                  # SQLAlchemy modely
├── schemas/                 # Pydantic v2 schémata
├── services/                # business logika
└── api/v1/                  # FastAPI routery
```

**Hard rule:** API endpointy dělají jen serializaci a auth/permissions. **Veškerá business logika je v `services/`**. Důvod: snazší testování (services lze volat přímo bez HTTP klienta) a oddělení transport vrstvy od domain logic.

## 6.2 Registrované routery (api/v1)

V `main.py` je registrováno cca 30 routerů. Klíčové:

| URL prefix | Soubor | Co dělá |
|------------|--------|---------|
| `/auth` | `auth.py` | register, login, refresh, logout, sms-otp, forgot-password, reset-password |
| `/totp` | `totp.py` | 2FA setup, enable, disable |
| `/users` | `users.py` | CRUD uživatelů (OZO admin) |
| `/tenant` | `tenant.py` | Info tenantu, GDPR export, delete |
| `/employees` | `employees.py` | CRUD + CSV import |
| `/plants`, `/workplaces`, `/job-positions` | `workplaces.py`, `job_positions.py` | Hierarchie + CSV import |
| `/risks` | `risks.py` | Legacy jednoduchý registr |
| `/risk-assessments` | `risk_assessments.py` | ČSN ISO 45001 hodnocení + measures + revisions |
| `/trainings` | `trainings.py` | Šablony, přiřazení, testy, certifikáty |
| `/revisions` | `revisions.py` | Revize zařízení, kalendář, QR |
| `/periodic-checks` | `periodic_checks.py` | Sanační kit, záchytné vany |
| `/medical-exams` | `medical_exams.py` | Lékařské prohlídky + auto-gen |
| `/accident-reports` | `accident_reports.py` | Úrazy + finalize + action items + photos |
| `/oopp` | `oopp.py` | OOPP grid + items + issues |
| `/operating-logs` | `operating_logs.py` | Provozní deníky |
| `/documents`, `/document-folders` | `documents.py`, `document_folders.py` | AI generátor BOZP dokumentů |
| `/dashboard` | `dashboard.py` | Agregát: pending reviews, expiring trainings, overdue revisions |
| `/billing/invoices` | `invoices.py` | Tenant vidí své faktury |
| `/audit` | `audit.py` | Cross-tenant audit (jen platform admin) |

## 6.3 Klíčové services (orientace)

`services/auth.py` — `register_user()`, `login_user()`, `_find_user_by_identifier()` (email globálně, personal_number per tenant, username globálně).

`services/refresh_tokens.py` — `issue_family()`, `rotate()`, reuse detection.

`services/risk_assessments.py` — RA CRUD + revision snapshot (JSONB) + `get_or_create_for_accident()` (placeholder RA pro úraz) + `_close_linked_accident_action_items()` (uzavře action items při RA → accepted).

`services/accident_reports.py` — úraz CRUD + `finalize_accident_report()` (multi-step: nastaví required_signers, generuje PDF, otevře signature flow, set status=final).

`services/accident_action.py` — `ensure_default_item()` (idempotentní, vytvoří default action item napojený na RA placeholder). Volá se z `create_accident_report` (od dubna 2026 i v draft fázi) a z `finalize_accident_report` (idempotentně).

`services/trainings.py` — template CRUD, `create_assignment_bulk()` (filtr plant/workplace/job_position/gender/role), `submit_test()` (grading, `score_pct`, set `valid_until`).

`services/medical_exams.py` — `_resolve_periodic_months()` (věk + kategorie z RFA → tabulka 79/2013), `reconcile_exams_for_employees_on_position()` (po změně kategorie pozice).

`services/oopp.py` — grid upsert (replace strategie), items CRUD, issues (linked na `RiskMeasure` při PPE measure).

`services/job_positions.py` — `create_job_position()` auto-vytvoří RFA stub.

`services/workplaces.py` — Plant + Workplace CRUD, RFA upsert (matrix 13 faktorů).

`services/employees.py` — CRUD, employee import CSV (`generate_template_csv()`, `import_from_csv()` s per-row savepoint).

`services/dashboard.py` — `get_dashboard()` agregace pro hlavní pohled.

`services/documents.py` — AI generátor (Anthropic API). Templates: `bozp_directive` (Směrnice), `training_outline` (Osnova), `revision_schedule` (Harmonogram), `risk_categorization`. 503 fallback pokud chybí `ANTHROPIC_API_KEY`.

`services/export_pdf.py` — generate_risks_pdf, generate_revisions_pdf, generate_accident_pdf, generate_medical_exams_pdf (fpdf2).

`services/signatures.py` — universal signature: `initiate_signature()` (3 auth metody: password / SMS OTP / public), `verify_signature()` (verify + create chain hash + uložit). Hash chain: `chain_hash = SHA256(prev_hash || canonical_payload)`.

## 6.4 Cross-module flow: Pracovní úraz

Příklad nejkomplexnějšího flow napříč 4 moduly:

1. `POST /accident-reports` (draft)
   - `services/accident_reports.create_accident_report()` ukládá záznam
   - **Volá `services/accident_action.ensure_default_item()`** (od dubna 2026)
     - Idempotentně vytvoří `AccidentActionItem` s titulem "Revize a případná změna rizik"
     - Volá `services/risk_assessments.get_or_create_for_accident()`
       - Pokud existuje RA pro pracoviště úrazu (status v draft/open/in_progress/mitigated): updatuje ji, set status=in_progress, log revision
       - Jinak: vytvoří placeholder RA (scope=workplace, hazard_category=other, P=3/S=3, status=draft)
     - Napojí action item přes `related_risk_assessment_id`
2. `POST /accident-reports/{id}/finalize`
   - Set `signature_required` + `required_signer_employee_ids`
   - Generuje PDF
   - Otevře signature flow
   - Status → final
3. OZO doplní detaily na placeholder RA
   - `PATCH /risk-assessments/{ra_id}` (např. specifikuje hazard_category, doplní reálné P/S)
   - Service vytvoří snapshot v `risk_assessment_revisions`
4. OZO přidá measures (eliminace, OOPP, školení)
   - `POST /risk-assessments/{ra_id}/measures`
   - Pokud `control_type=ppe` + `position_oopp_item_id`: service automaticky volá `services/oopp.create_employee_oopp_issues_for_position()` → výdeje OOPP postiženým zaměstnancům
5. OZO uzavře RA (riziko posouzeno a akceptováno)
   - `PATCH /risk-assessments/{ra_id}` s `status=accepted`
   - **Hook v service detekuje `previous != accepted && new == accepted`**
   - Volá `_close_linked_accident_action_items()` → najde všechny `AccidentActionItem` s `related_risk_assessment_id == ra.id` ve stavu pending/in_progress, set `status=done`, `completed_at=now`
   - Akční plán úrazu je teď uzavřený

\newpage

# 7. Frontend — struktura a konvence

## 7.1 Adresářová struktura

```
frontend/src/
├── app/
│   ├── (auth)/              # login, register, reset-password (centered card layout)
│   ├── (dashboard)/         # všechny moduly za auth wallem
│   │   ├── layout.tsx       # Sidebar + main content
│   │   ├── dashboard/page.tsx
│   │   ├── employees/page.tsx
│   │   ├── ...
│   ├── api/                 # Next.js API routes (proxy na backend)
│   ├── layout.tsx           # Root: <html>, QueryClientProvider, PWA setup
│   └── middleware.ts        # subdomain detection, redirect logic
├── components/
│   ├── ui/                  # Button, Card, Dialog, Input, Label, Badge, Tooltip, ...
│   └── layout/              # Header, Sidebar, ClientSwitcher, NotificationBell
├── lib/
│   ├── api.ts               # fetch wrapper (Bearer + cookie + CSRF)
│   ├── query-keys.ts        # invalidatePlants/Workplaces/Positions
│   ├── query-client.ts      # TanStack Query config
│   ├── use-table-sort.ts    # hook pro řazení tabulek
│   ├── offline-queue.ts     # PWA offline write queue
│   └── utils.ts             # cn() (clsx + tailwind-merge)
└── types/
    └── api.ts               # všechny TypeScript typy z backendu
```

## 7.2 Sidebar (NAV_ITEMS) a role-filtering

`components/layout/sidebar.tsx` definuje `NAV_ITEMS` array. Každá položka má:

- `href`, `label`, `icon` (lucide-react)
- `roles: Role[]` — filtr v runtime přes `useQuery("me")`

Položky (klíčové):

| Modul | Cesta | Role |
|-------|-------|------|
| Moji klienti | `/my-clients` | admin, ozo |
| Dashboard | `/dashboard` | ozo, hr_manager |
| Zaměstnanci | `/employees` | ozo, hr_manager |
| Lékařské prohlídky | `/medical-exams` | ozo, hr_manager |
| OOPP | `/oopp` | ozo, hr_manager, lead_worker |
| Pracovní úrazy | `/accident-reports` | ozo, hr_manager, lead_worker |
| Školení | `/trainings` | ozo, hr_manager |
| Školící centrum | `/trainings?view=my` | všichni |
| Revize | `/revisions` | ozo, hr_manager, equipment_responsible |
| Pravidelné kontroly | `/periodic-checks` | všichni |
| Provozní deníky | `/operating-logs` | všichni |
| Provozovny, pracoviště, pozice | `/workplaces` | ozo, hr_manager |
| Hodnocení rizik | `/risks` | ozo, hr_manager |
| Rizikové faktory na pracovištích | `/risk-overview` | ozo, hr_manager |
| Dokumenty | `/documents` | ozo, hr_manager |
| Fakturace | `/billing` | ozo, hr_manager |

## 7.3 Datový tok: API → TanStack → Component

Standardní vzor:

```tsx
// 1. Fetch
const { data: employees = [] } = useQuery<Employee[]>({
  queryKey: ["employees", "active"],
  queryFn: () => api.get("/employees?status=active"),
});

// 2. Mutation
const createMutation = useMutation({
  mutationFn: (data: EmployeeCreate) => api.post("/employees", data),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["employees"] });
    invalidatePositions(qc); // pokud mutace ovlivňuje pozice
  },
});

// 3. Form
const form = useForm<FormData>({ resolver: zodResolver(schema) });
```

## 7.4 QueryKey konvence

- `["entity"]` — list (default)
- `["entity", "active"]` — filtrovaný list (status, atd.)
- `["entity", id]` — detail
- `["entity", filtersObj]` — list s filtry

**Pravidlo:** Mutace v jednom modulu musí invalidovat všechny varianty queryKey, kde se daná entita zobrazuje. Pro sdílené entity (plants, workplaces, job_positions) se používají centrální helpery v `lib/query-keys.ts`:

```ts
import { invalidatePositions } from "@/lib/query-keys";

onSuccess: () => invalidatePositions(qc)
```

Tyto helpery invalidují **všechny historické varianty** queryKey (positions, job-positions, oopp-positions, risk-overview-positions). Vznikly jako fix po bugu, kdy nově vytvořená pozice nebyla viditelná v jiných modulech bez refresh stránky.

## 7.5 Formuláře: React Hook Form + Zod

```tsx
const schema = z.object({
  first_name: z.string().min(1, "Povinné pole"),
  employment_type: z.enum(["hpp", "dpp", "dpc", "external", "brigade"]),
  email: z.string().email().optional(),
});

type FormData = z.infer<typeof schema>;

const form = useForm<FormData>({ resolver: zodResolver(schema) });
```

Backend vrací chyby jako `{ detail: string | ValidationError[] }`. Frontend parsuje a zobrazuje per-field errors z `form.formState.errors`.

## 7.6 Dialog komponenta

Custom Dialog (bez radix-ui / shadcn). Vlastnosti:

- ESC zavírá
- Click-outside dismiss
- Scroll lock na body
- `size`: sm / md / lg / xl

```tsx
<Dialog open={open} onClose={() => setOpen(false)} title="Přidat zaměstnance" size="lg">
  <form onSubmit={form.handleSubmit(onSubmit)}>
    {/* fields */}
    <Button type="submit">Uložit</Button>
  </form>
</Dialog>
```

## 7.7 Auth flow ve frontend

`src/middleware.ts`:

1. Extrahuje tenant slug ze subdomény → `x-tenant-slug` header
2. Reserved subdomains (`admin`, `www`, `api`) → `x-tenant-reserved` flag
3. **Public paths** (`/login`, `/register`, `/reset-password`): bez tokenu OK; pokud má token → redirect `/`
4. **Protected paths**: bez tokenu → `/login?next={pathname}`
5. Token presence: čte `access_token` httpOnly cookie

**Token storage:**

- httpOnly access_token cookie — posílá se automaticky
- CSRF cookie (non-httpOnly) — JS čte pro `X-CSRF-Token` header
- Login + register backend vrací `{ access_token, refresh_token }` v JSON i v cookies — frontend si ukládá Bearer pro API klienty / TanStack i nadále, cookies se používají při browser navigation

## 7.8 Speciální moduly (highlights)

**Dashboard** (`/dashboard/page.tsx`):

- Stat karty (pending_risk_reviews, expiring_trainings, overdue_revisions, draft_accidents, prošlé revize/kontroly)
- Calendar tabulka (90 dní dopředu)
- Onboarding wizard (Plant → Workplace → Position)

**Risk Assessment** (`/risks/page.tsx`):

- 5×5 heatmap (P × S, počty rizik v buňce)
- Filter chips (status, level)
- Detail modal s measures CRUD a revisions snapshot
- Form má 21 hazard_category options

**Trainings** (`/trainings/page.tsx`):

- Admin view: správa šablon + approval workflow
- Employee view (`?view=my`): absolvování + test + certifikát
- Test dialog: otázky za sebou, submit → score → certifikace
- Universal signature pro absolvování

**Employees** (`/employees/page.tsx`):

- CRUD + CSV import s auto-account creation (Server vygeneruje plaintext heslo, vrátí jednou v response)
- Filter chips (status, plant, workplace, position, gender)
- Role assign s pravidly (HR nemůže udělat OZO/HR z někoho jiného)

\newpage

# 8. Migrace (Alembic)

## 8.1 Workflow

Soubory v `backend/migrations/versions/NNN_nazev.py`. Číslování je **strictly sequential** (001, 002, ...). Aktuální head: 066.

Příklady milníků:

| Migrace | Co přidává |
|--------:|------------|
| 001 | Tenants, users, audit_log + RLS policies |
| 016 | TOTP encrypted secret |
| 022 | Trainings JSONB test_questions |
| 041 | Signature canvas pro školení (legacy) |
| 057-058 | Universal signatures (hash chain) + accident external participants |
| 060 | Training approval workflow (status pending_approval) |
| 061 | Login SMS OTP (cross-tenant) |
| 063 | User.email NULLABLE (subdomain login) |
| 066 | Risk assessments + measures + revisions + FK na accident_action_items |

## 8.2 Pravidla psaní migrací

- Vždy navazovat na `head` (`alembic revision -m "..." --autogenerate`)
- `down_revision = "NNN-1"` (předchozí číslo)
- `revision = "NNN"` (nové číslo)
- Per-file ignore E501 v `pyproject.toml` (long lines OK v migracích)
- DDL musí být idempotentní pokud možno (CREATE TABLE IF NOT EXISTS apod. jen kde dává smysl)
- RLS policy se vytváří v migraci, ne v kódu
- GENERATED columns: viz migrace 066 (`initial_score = P × S` PERSISTED)

## 8.3 Spouštění

```bash
# Lokálně přes docker
docker compose exec backend alembic upgrade head

# Vytvoření nové migrace
docker compose exec backend alembic revision -m "add_field_x"

# Status
docker compose exec backend alembic current
docker compose exec backend alembic history
```

\newpage

# 9. Testování

## 9.1 Filozofie

**Real DB, žádné mocky.** PostgreSQL v testech běží jako samostatný kontejner. Důvody:

- RLS politiky se nedají mockovat — musí se ověřit, že tenant A nevidí data tenantu B
- Audit log se testuje s reálným SQLAlchemy event listenerem
- GENERATED columns + DB triggery se musí testovat na PG

## 9.2 conftest.py — fixture pattern

Klíčové fixtures:

```python
@pytest.fixture(scope="session")
async def test_engine():
    """Async engine na test DB."""

@pytest.fixture
async def db_connection(test_engine):
    """Open connection, BEGIN transaction.
    Při teardown: ROLLBACK — testy jsou izolované, data se necommitují."""

@pytest.fixture
async def db_session(db_connection):
    """AsyncSession s join_transaction_mode=create_savepoint.
    Když endpoint volá session.commit(), vytvoří se SAVEPOINT
    místo committu vnější transakce."""

@pytest.fixture
async def client(db_session):
    """AsyncClient s ASGI transportem.
    Override FastAPI get_db dependency na db_session."""
```

## 9.3 Test helpers

```python
async def _ozo_headers(client, suffix=""):
    """Registruje OZO uživatele v novém tenantě, vrátí Bearer headers."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": f"ozo-{suffix}@firma.cz",
        "password": "heslo1234",
        "tenant_name": f"Firma {suffix}",
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
```

Každý test začíná `headers = await _ozo_headers(client, "unique-suffix")` — izolace per test.

## 9.4 Pokrytí

Cca 30+ test souborů v `backend/tests/`:

- `test_auth.py` — register, login, me, refresh
- `test_refresh_rotation.py` — rotation, reuse detection, family revocation
- `test_csrf.py` — Bearer bypass, cookie auth, mismatched token
- `test_rate_limit.py` — slowapi, progressive delay
- `test_audit_log.py` — CREATE/UPDATE/DELETE audit, sensitive columns skip
- Domain CRUD: `test_employees.py`, `test_risks.py`, `test_workplaces.py`, `test_trainings.py`, `test_medical_exams.py`, `test_accident_reports.py`, `test_revisions.py`, `test_periodic_checks.py`, `test_oopp.py`, `test_risk_assessments.py`
- `test_admin.py` — platform admin bypass, cross-tenant
- `test_fk_validation.py` — assert_in_tenant, cascade delete
- `test_dashboard.py` — agregace

## 9.5 Příklad: invariant úraz ↔ RA

```python
async def test_accident_create_auto_links_risk_assessment(client):
    """Vytvoření úrazu (i v draft fázi) musí automaticky:
    1) vytvořit AccidentActionItem 'Revize a případná změna rizik'
    2) vytvořit/najít placeholder RiskAssessment
    3) napojit action item přes related_risk_assessment_id na to RA."""
    headers = await _ozo_headers(client, "11")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=ACCIDENT_PAYLOAD, headers=headers,
    )
    accident_id = create_resp.json()["id"]
    items_resp = await client.get(
        f"/api/v1/accident-reports/{accident_id}/action-items", headers=headers,
    )
    default_items = [i for i in items_resp.json() if i.get("is_default")]
    assert len(default_items) == 1
    assert default_items[0]["status"] == "pending"
    assert default_items[0]["related_risk_assessment_id"] is not None
```

\newpage

# 10. CI/CD a vývojové prostředí

## 10.1 GitHub Actions (`.github/workflows/backend.yml`)

Steps:

1. Checkout
2. Setup Python 3.12
3. Install `uv` (fast dependency resolver)
4. `uv pip install -e ".[dev]"`
5. **Lint:** `ruff check .` (E, F, I, N, W, UP rules)
6. **Type check:** `mypy app` (strict, pydantic plugin)
7. **Migrations:** `alembic upgrade head`
8. **Tests:** `pytest -v`

Services in CI: PostgreSQL 16 (pgvector image) + Redis 7. Env: `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `REDIS_URL`, `ENVIRONMENT=test`.

Frontend pipeline (`.github/workflows/frontend.yml`): checkout, npm ci, eslint, tsc --noEmit, next build.

## 10.2 Lint pravidla

**ruff** (`pyproject.toml`):

- Target Python 3.12
- Line length 100
- Rules: E, F, I, N, W, UP
- Per-file ignores: `migrations/*` (E501), `tests/*` (E501)

**mypy** (`pyproject.toml`):

- `strict = true`
- `plugins = ["pydantic.mypy"]`
- Žádné `Optional[X]` (používat `X | None`)
- `# type: ignore[no-any-return]` jen pro jose jwt volání

**Frontend ESLint:**

- Extends `next/core-web-vitals`
- Žádné `interface Foo extends Bar {}` (prázdné) — používat `type Foo = Bar`

## 10.3 Docker Compose (dev)

`docker-compose.yml` definuje:

- **db** (`pgvector/pgvector:pg16`): port 5432, volume `postgres_data`, healthcheck `pg_isready`
- **redis** (`redis:7-alpine`): port 6379
- **backend** (build `./backend`, Dockerfile.dev): volume mount `./backend:/app`, command `uvicorn app.main:app --reload`
- **frontend** (build `./frontend`, Dockerfile.dev): volume mount `./frontend:/app`, node_modules volume

Volume `postgres_data` zajišťuje persistence DB mezi `docker compose down`.

## 10.4 Lokální spuštění

```bash
# První spuštění
git clone git@github.com:lukasvoracek/bozoapp.git
cd bozoapp
cp .env.example .env  # upravit env vars
docker compose up -d db redis
docker compose run --rm backend alembic upgrade head
docker compose up

# Frontend dev s hot reload
docker compose up frontend  # nebo: cd frontend && npm run dev

# Backend dev s hot reload
docker compose up backend   # uvicorn --reload

# Spustit testy
docker compose exec backend pytest

# Lint
docker compose exec backend ruff check .
docker compose exec backend mypy app
```

## 10.5 Production deploy (plánované)

- Hetzner Cloud server (CX22 → CX42 dle růstu)
- Docker Compose s production konfigurací (`docker-compose.prod.yml`)
- Caddy reverse proxy: `:443 → backend:8000` (`/api/*`) + `frontend:3000` (zbytek)
- TLS přes ACME (Let's Encrypt), wildcard pro `*.digitalozo.cz`
- Backupy: postgres-backup-s3 cron, S3 lifecycle 30 dní
- Sentry: production DSN v env
- Monitoring: Hetzner Cloud Monitoring + uptime checks (Better Stack / UptimeRobot)

\newpage

# 11. Onboarding nového vývojáře

## 11.1 Den 1

1. Naklonovat repo, spustit Docker Compose
2. Přečíst si `CLAUDE.md` (Project Instructions) v rootu
3. Vytvořit OZO uživatele přes `/auth/register` (lokálně `firma1.localhost`)
4. Projít UI hlavních modulů: zaměstnanci → pracoviště → pozice → riziková hodnocení → školení
5. Spustit `pytest` — ověřit, že vše prochází

## 11.2 Den 2-3: První feature

Doporučený exercise: přidat nový sloupec do `Employee` (např. `note: str | None`).

Kroky:

1. Migrace: `docker compose exec backend alembic revision -m "add_employee_note"`
2. SQLAlchemy model `models/employee.py`: přidat `note: Mapped[str | None]`
3. Pydantic schémata `schemas/employees.py`: přidat do create/update/response
4. Service `services/employees.py`: pokud potřeba, jinak Pydantic update funguje out-of-box
5. API endpoint zůstává stejný (Pydantic dělá validaci)
6. Frontend `types/api.ts`: přidat `note: string | null`
7. Frontend `app/(dashboard)/employees/page.tsx`: přidat input do form a sloupec do tabulky
8. Pytest: rozšířit `test_employees.py` o test note field
9. `docker compose exec backend alembic upgrade head`
10. Commit + push → CI → review

## 11.3 Hard rules — co NIKDY nedělat

- **Nikdy nemockovat DB v testech** (RLS by se zapomnělo otestovat)
- **Nikdy nepoužít `Optional[X]`** — vždy `X | None` (mypy strict)
- **Nikdy nezapomenout `tenant_id` filtr** v service (RLS je defense-in-depth, ne primární)
- **Nikdy neukládat plaintext heslo** — Argon2id přes `hash_password()`
- **Nikdy nepřidat sloupec bez migrace** — Alembic + DB musí matchovat model
- **Nikdy neporušit invariant úraz ↔ RA** — `ensure_default_item()` se musí volat při create úrazu
- **Nikdy nepoužít `try/except: pass`** — silent except polyká chyby a maskuje bugy

## 11.4 Co DĚLAT

- Při návrhu nové entity si rozmyslet `tenant_id`, RLS policy, indexy, FK ON DELETE
- Pro sdílené entity (plants, workplaces, positions) použít centrální helpery `invalidate*()` v `lib/query-keys.ts`
- Pro nové role guardy použít `require_role("ozo", "hr_manager")` v `core/permissions.py`
- Pro cross-tenant FK validace volat `assert_in_tenant(db, Model, fk_id, tenant_id)`
- Pro audit-relevant operace nebrouzdat — `before_flush` listener to zachytí automaticky
- Pro dokumentaci API: FastAPI auto-generuje OpenAPI v `/docs` a `/redoc`

## 11.5 Komunikace s týmem

- Krátké úkoly: GitHub Issues
- Větší změny architektury: ADR v `/docs/adr/NNNN-titul.md` (Architecture Decision Record)
- Bugfixy: PR s odkazem na issue
- Code review: vyžaduje 1 approval, lint + tests musí být zelené

\newpage

# 12. Glosář

| Pojem | Význam |
|-------|--------|
| **OZO** | Odborně způsobilá osoba v BOZP (Zákoník práce §9) |
| **BOZP** | Bezpečnost a ochrana zdraví při práci |
| **PO** | Požární ochrana |
| **RA** | Risk Assessment (hodnocení rizika dle ISO 45001) |
| **RFA** | Risk Factor Assessment (kategorizace prací dle NV 361/2007) |
| **OOPP** | Osobní ochranné pracovní prostředky (NV 390/2021) |
| **SÚIP** | Státní úřad inspekce práce |
| **eIDAS** | EU regulace o elektronické identifikaci a důvěryhodných službách |
| **ZES** | Zaručený elektronický podpis |
| **TSA** | Time Stamping Authority (RFC 3161) |
| **RLS** | Row-Level Security (PostgreSQL) |
| **JTI** | JWT ID (unique identifier of token) |
| **HPP / DPP / DPČ** | Hlavní pracovní poměr / dohoda o provedení práce / dohoda o pracovní činnosti |
