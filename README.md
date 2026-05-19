# T-Cash

> **Save Together. Build Credit. Grow Business.**

T-Cash is a group savings, credit intelligence, and SME financial growth platform built for the East African market. It digitises *chama* and group savings workflows, then layers intelligence on top — turning contribution history into credit scores, pooled savings into investment guidance, and informal savings groups into structured SME finance vehicles.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Modules](#modules)
- [API Reference](#api-reference)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running with Docker](#running-with-docker)
- [Celery & Background Tasks](#celery--background-tasks)
- [Security Architecture](#security-architecture)
- [Development Phases](#development-phases)
- [USSD Interface](#ussd-interface)
- [Contributing](#contributing)

---

## Overview

T-Cash solves a real gap in the East African fintech market:

| Problem | Competitors | T-Cash Solution |
|---|---|---|
| Savings data goes unused | Collects, then discards | Builds a credit score from it |
| No SME pathway | No business tools | SME profiles + loan matching |
| No investment guidance | Collect only | AI investment matching |
| Fraud / collapse risk | No governance tools | Multi-sig + trust scoring |
| Rural exclusion | Smartphone only | USSD fallback channel |
| Diaspora locked out | Kenya-local only | Forex + diaspora flow |

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Backend API | Django + Django REST Framework | Battle-tested, fast to build, huge ecosystem |
| Auth | JWT via SimpleJWT + OTP (Africa's Talking) | Phone-first auth; works offline via USSD |
| Database | PostgreSQL | ACID compliant, handles financial transactions safely, supports JSON fields |
| Task Queue | Celery + Redis | Async OTP sending, payment processing, scheduled reminders |
| Cache | Redis | Session caching, OTP expiry management, rate limiting |
| Frontend Web | React (TypeScript) | Component-based; React Native reuse for mobile |
| Mobile App | React Native | Shares 60–70% of web logic — cheapest path to iOS + Android |
| USSD | Africa's Talking USSD API | Handles session state for feature phone users automatically |
| Payments | M-Pesa Daraja API + Pesalink | Mandatory for Kenyan market — STK Push for seamless payments |
| Storage | AWS S3 / Cloudflare R2 | Document uploads (ID verification, SME docs) |
| Infra | Docker + Railway/Render → AWS ECS (prod) | Scalable production deployments |
| Monitoring | Sentry + Django Silk | Error tracking and query performance profiling |
| CI/CD | GitHub Actions | Automated testing and deployment pipeline |

---

## Project Structure

```
tcash/
├── config/                  # Django project settings, URLs, Celery config
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   ├── wsgi.py
│   └── asgi.py
│
├── users/                   # Module 1 — Authentication & user profiles
│   ├── models.py            #   User (phone-based), OTPCode
│   ├── views.py             #   OTP request/verify, profile, PIN setup
│   ├── serializers.py
│   ├── urls.py
│   ├── sms_service.py       #   Africa's Talking SMS wrapper
│   └── migrations/
│
├── groups/                  # Module 2 — Chama / savings group management
│   ├── models.py            #   Group, GroupMember, WithdrawalRequest, WithdrawalVote, MemberTrustScore
│   ├── views.py             #   Create/join/manage groups, multi-sig withdrawals
│   ├── serializers.py
│   ├── urls.py
│   └── migrations/
│
├── contributions/           # Module 3 — Contribution cycles & payments
│   ├── models.py            #   ContributionCycle, Contribution, ContributionReversal, RotationSchedule, Badge
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── migrations/
│
├── payments/                # Module 4 — M-Pesa integration & treasury
│   ├── models.py            #   Transaction, GroupTreasury, TreasuryLedgerEntry, Disbursement
│   ├── views.py             #   Treasury detail, trigger disbursement, B2C callbacks, transaction history
│   ├── serializers.py
│   ├── tasks.py             #   Celery: process_disbursement, handle_b2c_result
│   ├── mpesa.py             #   Daraja API client (STK Push + B2C)
│   └── migrations/
│
├── notifications/           # Module 7 — Smart nudge engine
│   ├── models.py            #   Notification, NotificationPreference
│   ├── views.py             #   List, mark-read, preferences, push token registration
│   ├── service.py           #   Centralised dispatcher (SMS, push, in-app)
│   ├── tasks.py             #   Celery Beat: reminders, overdue alerts, re-engagement nudges
│   ├── admin.py
│   └── migrations/
│
├── analytics/               # Module 8 — Dashboards (Phase 2)
├── core/                    # Module 9 — SME business profiles (Phase 2–3)
│
└── manage.py
```

---

## Modules

### Module 1 — Users & Authentication (`users/`)

Phone-number-first authentication using OTP codes delivered via SMS.

**Authentication flow:**
1. `POST /api/users/request-otp/` — generates a 6-digit OTP and sends it via Africa's Talking SMS
2. `POST /api/users/verify-otp/` — validates OTP, issues JWT access token (15 min) + refresh token (7 days)
3. `POST /api/users/token/refresh/` — silently issues a new access token
4. `POST /api/users/logout/` — blacklists the refresh token

**KYC tier system:**

| Tier | Requirements | Unlocks |
|---|---|---|
| 0 | Phone number only | Basic group membership |
| 1 | Name + National ID provided | Higher transaction limits |
| 2 | ID verified by admin | Full platform access |

**Security controls:**
- OTP rate limit: max 3 requests per phone per 10 minutes
- OTP brute-force: max 5 wrong attempts → account locked for 30 minutes
- Phone numbers validated in E.164 format (`+254XXXXXXXXX`)
- 4-digit PIN for in-app payment confirmations — stored hashed via `make_password()` (bcrypt)
- All passwords and PINs are **never** stored in plain text

---

### Module 2 — Groups & Chama Management (`groups/`)

Full lifecycle management of savings groups (chamas), including multi-signature withdrawal governance.

**Group types:**
- `ROTATING` — Merry-go-round: pool paid out to one member per cycle in rotation order
- `FIXED` — Fixed pool: shared savings without mandatory rotation
- `INVESTMENT` — Investment club: pooled funds for investment decisions

**Key features:**
- Groups created with a unique 6-character invite code (invalidated when group is full)
- Join requests require admin approval
- Roles: `ADMIN`, `TREASURER`, `SIGNATORY`, `MEMBER`
- Configurable `withdrawal_quorum` — number of signatory approvals required to release funds
- Full audit log (`GroupAuditLog`) on all significant actions (immutable)
- **MemberTrustScore** — calculated monthly from on-time rate (40%), tenure (20%), withdrawal behaviour (20%), dispute history (20%)

**Multi-sig withdrawal flow:**
1. Any member submits a withdrawal request with amount + reason
2. Signatories and admin are notified via push + SMS
3. Each signatory casts an `APPROVE` or `REJECT` vote (one vote per person)
4. On reaching `withdrawal_quorum` approvals → status moves to `APPROVED`
5. A single rejection → status flagged for admin review
6. Admin triggers disbursement → funds sent via M-Pesa B2C

---

### Module 3 — Contributions (`contributions/`)

Tracks every member payment across contribution cycles, with streak tracking and gamification badges.

**Contribution lifecycle:**
1. Admin creates a `ContributionCycle` with a `due_date`
2. Member taps "Pay" → M-Pesa STK Push triggered
3. M-Pesa callback validated → `Contribution` record created
4. Status set to `PAID` (on time) or `LATE` (after due date)
5. Streak counter updated; badges awarded at milestones

**Streak & badge milestones:**

| Streak | Badge |
|---|---|
| 3 consecutive on-time | 🔥 3-Month Streak |
| 6 consecutive on-time | ⭐ 6-Month Streak |
| 12 consecutive on-time | 🏆 12-Month Streak |

**Contribution statuses:** `PENDING` → `PAID` / `LATE` / `MISSED` / `REVERSED`

**Reversals** require dual approval (admin + treasurer) via `ContributionReversal`. The original contribution record is never deleted or edited — a separate reversal record is created instead.

**Rotating pool logic (`RotationSchedule`):**
- Admin sets the payout order at group creation or by vote
- System tracks whose turn it is to receive the pool
- Members who missed a cycle are skipped and moved to the next cycle
- Pool automatically disbursed to the next recipient on cycle completion

---

### Module 4 — Payments & Disbursement (`payments/`)

All M-Pesa integration lives here. The `GroupTreasury` is the single source of truth for a group's funds.

**Treasury operations:**
- `credit(amount)` / `debit(amount)` — atomic F() expressions to prevent race conditions
- Double-entry style `TreasuryLedgerEntry` for every movement
- Daily disbursement limit (configurable per group, default KES 50,000)

**M-Pesa STK Push (C2B — member paying in):**
```
POST /api/payments/stk-push/
```
Triggers a Lipa na M-Pesa prompt on the member's phone. The Daraja callback webhook validates the Safaricom HMAC signature before updating the contribution record.

**B2C Disbursement (T-Cash paying out to member):**
- Always executed asynchronously via Celery — never in a request cycle
- Retry policy: up to 3 attempts with 1-hour backoff
- Fraud check: rejects if the same phone received ≥ 3 disbursements in 24 hours
- On final failure: marks disbursement `FAILED` and triggers admin alert

**Disbursement types:** `ROTATION` (merry-go-round payout), `WITHDRAWAL` (approved request), `LOAN` (Phase 2)

---

### Module 7 — Notifications & Nudges (`notifications/`)

Centralised notification dispatcher with per-user channel preferences.

**Channels:** In-App · SMS (Africa's Talking) · Push (FCM/APNs)

**Smart Nudge Engine (Celery Beat — scheduled tasks):**

| Trigger | Action | Schedule |
|---|---|---|
| 3 days before due date | Reminder push + SMS | Daily 08:00 EAT |
| 1 day after due date | Overdue alert push + SMS | Daily 09:00 EAT |
| Cycle 7+ days overdue | Mark contributions MISSED, close cycle | Daily 10:00 EAT |
| No login for 14 days | Re-engagement push + SMS | Every Monday 09:00 EAT |

**Security constraints:**
- SMS messages **never** include raw monetary amounts (fraud interception risk)
- No marketing messages without explicit opt-in (GDPR-aligned)
- Push tokens refreshed on every app login

---

## API Reference

### Authentication

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| POST | `/api/users/request-otp/` | Request OTP via SMS | Public |
| POST | `/api/users/verify-otp/` | Verify OTP, receive JWT tokens | Public |
| POST | `/api/users/token/refresh/` | Refresh access token | Public |
| POST | `/api/users/logout/` | Blacklist refresh token | Bearer |
| GET/PUT | `/api/users/profile/` | View or update profile & KYC | Bearer |
| POST | `/api/users/setup-pin/` | Set 4-digit payment PIN | Bearer |
| POST | `/api/users/verify-pin/` | Verify payment PIN | Bearer |

### Groups

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| GET/POST | `/api/groups/` | List my groups / create group | Bearer |
| GET/PATCH | `/api/groups/<id>/` | Get or update group settings | Bearer |
| POST | `/api/groups/join/` | Join via invite code | Bearer |
| GET | `/api/groups/<id>/members/` | List group members | Bearer |
| POST | `/api/groups/<id>/members/<mid>/approve/` | Approve or reject join request | Bearer (Admin) |
| POST | `/api/groups/<id>/members/<mid>/role/` | Update member role | Bearer (Admin) |
| GET/POST | `/api/groups/<id>/withdrawals/` | List or create withdrawal request | Bearer |
| POST | `/api/groups/<id>/withdrawals/<rid>/vote/` | Cast approval/rejection vote | Bearer (Signatory/Admin) |

### Payments

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| GET | `/api/payments/treasury/<group_id>/` | Treasury balance + ledger | Bearer |
| POST | `/api/payments/groups/<gid>/disburse/<wid>/` | Trigger B2C disbursement | Bearer (Admin) |
| POST | `/api/payments/b2c/result/` | Safaricom B2C result callback | Signature |
| POST | `/api/payments/b2c/timeout/` | Safaricom timeout callback | Signature |
| GET | `/api/payments/transactions/` | My transaction history | Bearer |
| GET | `/api/payments/groups/<id>/disbursements/` | Group disbursements | Bearer (Admin/Treasurer) |

### Notifications

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| GET | `/api/notifications/` | In-app notifications (50 most recent) | Bearer |
| POST | `/api/notifications/mark-read/` | Mark one or all as read | Bearer |
| GET/PATCH | `/api/notifications/preferences/` | View or update channel preferences | Bearer |
| POST | `/api/notifications/push-token/` | Register FCM/APNs device token | Bearer |

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- An [Africa's Talking](https://africastalking.com) account (sandbox available)
- A [Safaricom Daraja](https://developer.safaricom.co.ke) account (sandbox available)

### Local setup

```bash
# 1. Clone the repo
git clone https://github.com/your-org/tcash.git
cd tcash

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and configure environment variables
cp .env.example .env
# Edit .env with your credentials (see Environment Variables below)

# 5. Apply database migrations
python manage.py migrate

# 6. Create a superuser (for Django admin)
python manage.py createsuperuser

# 7. Run the development server
python manage.py runserver
```

The API is now available at `http://127.0.0.1:8000/`.

### Quick smoke test

```bash
python test_login.py
```

This sends a test OTP request to `/api/users/request-otp/`. In `DEBUG=True` mode, the generated OTP is returned in the response body for easy local testing.

---

## Environment Variables

Create a `.env` file in the project root. All variables are loaded via `python-decouple`.

```dotenv
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
DB_NAME=tcash_db
DB_USER=postgres
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432

# Africa's Talking (SMS + USSD)
AT_USERNAME=sandbox
AT_API_KEY=your-at-api-key

# Safaricom Daraja (M-Pesa)
MPESA_ENV=sandbox                         # sandbox | production
MPESA_CONSUMER_KEY=
MPESA_CONSUMER_SECRET=
MPESA_SHORTCODE=174379
MPESA_PASSKEY=
MPESA_CALLBACK_URL=https://your-domain.com/api/payments/stk/callback/
MPESA_B2C_SHORTCODE=
MPESA_B2C_INITIATOR_NAME=
MPESA_B2C_SECURITY_CREDENTIAL=
MPESA_B2C_RESULT_URL=https://your-domain.com/api/payments/b2c/result/
MPESA_B2C_QUEUE_TIMEOUT_URL=https://your-domain.com/api/payments/b2c/timeout/
MPESA_CALLBACK_SECRET=your-hmac-secret

# Firebase Cloud Messaging (Push notifications)
FCM_SERVER_KEY=

# Celery / Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

> **Never commit `.env` to version control.** It is already in `.gitignore`.

---

## Running with Docker

```bash
# Build and start all services (Django, PostgreSQL, Redis, Celery worker, Celery Beat)
docker compose up --build

# Run migrations inside the container
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser
```

---

## Celery & Background Tasks

T-Cash uses Celery for all asynchronous and scheduled operations. Redis is both the broker and result backend.

### Starting workers locally

```bash
# Celery worker (processes async tasks)
celery -A config worker --loglevel=info

# Celery Beat (runs the scheduled nudge engine)
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Scheduled tasks (Celery Beat)

| Task | Schedule (EAT) | Description |
|---|---|---|
| `notifications.tasks.send_contribution_reminders` | Daily 08:00 | Remind members with unpaid contributions due in 3 days |
| `notifications.tasks.send_overdue_alerts` | Daily 09:00 | Alert members whose contribution was due yesterday |
| `notifications.tasks.mark_missed_contributions` | Daily 10:00 | Close cycles 7+ days overdue; mark unpaid as MISSED |
| `notifications.tasks.send_reengagement_nudges` | Monday 09:00 | Re-engage members inactive for 14+ days |

### Async tasks (triggered by events)

| Task | Triggered by |
|---|---|
| `payments.tasks.process_disbursement` | Admin approves withdrawal → B2C sent to M-Pesa |
| `payments.tasks.handle_b2c_result` | Safaricom B2C result webhook received |
| `notifications.tasks.notify_withdrawal_signatories` | New withdrawal request created |
| `notifications.tasks.notify_member_joined` | New member join request submitted |
| `notifications.tasks.notify_contribution_confirmed` | M-Pesa callback confirms payment |

---

## Security Architecture

T-Cash is a financial application. These rules apply globally and are non-negotiable:

| Area | Rule |
|---|---|
| **HTTPS** | `SECURE_SSL_REDIRECT=True`, HSTS headers, no HTTP in production |
| **Database** | All financial writes use atomic transactions. No raw SQL with f-strings — always use the Django ORM |
| **API design** | All endpoints authenticated except `/request-otp/` and `/verify-otp/`. No sensitive data in URLs |
| **Input validation** | All serializer fields explicitly typed and whitelisted. `request.data` never passed directly to a model |
| **Secrets** | All credentials in `.env` via `python-decouple`. Rotated quarterly. Never committed to git |
| **OTP** | Max 3 requests per phone per 10 minutes; max 5 wrong attempts → 30-minute account lock |
| **JWT** | Access token: 15 min. Refresh token: 7 days, rotated on use, blacklisted on logout |
| **Payments** | M-Pesa callbacks validated via HMAC-SHA256 signature before processing |
| **Disbursements** | Fraud check: same phone cannot receive ≥ 3 disbursements in 24 hours |
| **Logging** | All auth events, payment events, and admin actions logged with actor + IP + timestamp |
| **Data residency** | All data stored in Nairobi AWS region (`af-south-1`) for data sovereignty compliance |
| **GDPR** | User data deletion endpoint, data export endpoint, consent logging for third-party sharing |
| **Dependencies** | `pip-audit` run in CI pipeline on every push. Critical vulnerabilities block deployment |

---

## Development Phases

### Phase 1 — Foundation (Months 1–3) ✅ *In progress*

Core saving and disbursement MVP. Groups can save and disburse money securely.

- Complete Users module: KYC tiers, PIN setup, token blacklisting
- Complete Groups module: creation, joining, multi-sig rules, trust scoring
- Complete Contributions module: M-Pesa STK Push webhook, streak tracking
- Complete Payments module: B2C disbursement, group treasury ledger
- Basic Notifications: SMS + push for contribution reminders

**Deliverable:** Working MVP — groups can save and disburse money securely.

### Phase 2 — Intelligence Layer (Months 4–6)

Credit scoring, investment matching, USSD, and diaspora flows.

- Build `credit/` app: credit score engine, loan readiness report, partner lender integration
- Build `investments/` app: product catalogue, matching engine, goal modelling
- Expand `analytics/`: member dashboard, group admin dashboard, financial insights
- Expand `notifications/`: smart nudge engine, behavioural triggers
- USSD interface via Africa's Talking USSD API
- Diaspora remittance flow (Wise/Flutterwave integration)

**Deliverable:** Credit scores live, first loan applications, investment matching active.

### Phase 3 — Growth & SME (Months 7–12)

Full platform launch on web + mobile with SME lending partnerships.

- SME profiles in `core/`: business registration, SME loan readiness
- Financial education content layer
- React Native mobile app (iOS + Android) using existing DRF API
- WhatsApp Business API integration for group digests
- Platform analytics dashboard (internal)
- Third-party security audit / penetration test

**Deliverable:** Full platform live on web + mobile. SME lending partnerships active.

---

## USSD Interface

USSD (`*XXX#`) allows any feature phone user — rural members, low-literacy users, older chama members — to access core T-Cash features without a smartphone or data connection. This expands the addressable market from ~10M smartphone users to ~40M mobile subscribers in Kenya.

**USSD menu (Phase 2):**

| Option | Action |
|---|---|
| 1. Check Balance | Shows member's group balance and next contribution due date |
| 2. Pay Contribution | Triggers M-Pesa STK Push for the current cycle |
| 3. My Groups | Lists all groups the member belongs to with their role |
| 4. Approve Withdrawal | Signatories can cast votes on pending withdrawal requests |
| 5. My Credit Score | Reads back the member's credit score tier (Poor / Fair / Good / Excellent) |
| 6. Contact Admin | Sends SMS to the group admin with the member's name |
| 0. Exit | Ends the USSD session |

---

## Contributing

1. Fork the repository and create a feature branch from `main`
2. Follow the existing code style — Django ORM only, no raw SQL
3. All financial logic must use database-level atomic transactions
4. Write tests for any new model logic, serializer, or view
5. Run `pip-audit` before submitting a PR — no critical vulnerabilities
6. Ensure `DEBUG=False` behaviour is tested before submitting
7. Open a pull request with a clear description of what changed and why

---

*T-Cash — Version 1.0 | March 2026 | Confidential — Internal Use Only*
