# Billing System

This project is a Stripe-backed billing and entitlement service designed
to manage subscriptions, pricing, and feature access in a clean and
maintainable way.

---

## Current Architecture Overview

### Core Concepts

**Subscriptions** Represent a user's billing relationship and lifecycle
state.

**Entitlements** Represent feature access granted by pricing plans,
trials, or manual overrides.

**Webhook Processing** Stripe acts as an external event source and
drives subscription lifecycle updates.

**Async Processing** Celery is used for retryable tasks and
reconciliation jobs.

---

## Setup

### Option 1: Docker (Recommended)

Docker Compose will spin up all required services automatically: the Django web server, PostgreSQL, Redis, RabbitMQ, a Celery worker, and Celery Beat.

**Prerequisites:**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose) — or Docker Engine + Compose plugin on Linux

**Steps:**

1. Copy the example environment file and fill in your Stripe credentials:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` and set at minimum:

   ```env
   # Django
   DJANGO_SECRET_KEY=your-secret-key-here
   DEBUG=True

   # Postgres (used by all services)
   POSTGRES_DB=billing
   POSTGRES_USER=billing
   POSTGRES_PASSWORD=billing

   # Redis
   REDIS_URL=redis://redis:6379/0

   # RabbitMQ
   RABBITMQ_USER=guest
   RABBITMQ_PASSWORD=guest
   CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
   CELERY_RESULT_BACKEND=redis://redis:6379/1

   # Celery
   CELERY_APP=billing
   CELERY_LOG_LEVEL=info
   CELERY_WORKER_CONCURRENCY=2
   CELERY_BEAT_SCHEDULER=django_celery_beat.schedulers:DatabaseScheduler

   # Stripe
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

3. Start all services:

   ```bash
   docker compose up
   ```

   Or run in the background:

   ```bash
   docker compose up -d
   ```

4. In a separate terminal (or after detaching), run migrations:

   ```bash
   docker compose exec web python manage.py migrate
   ```

5. The API is now available at [http://localhost:8000](http://localhost:8000).
   Interactive docs at [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/).

**Useful Docker commands:**

```bash
# View logs for all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f web
docker compose logs -f celery_worker

# Stop all services
docker compose down

# Stop and remove volumes (wipes the database)
docker compose down -v

# Rebuild images after dependency changes
docker compose up --build
```

---

### Option 2: Local Development

Run everything directly on your machine. You will need to install and manage PostgreSQL, Redis, and RabbitMQ yourself, or point the app at existing instances.

**Prerequisites:**

- Python 3.11+
- PostgreSQL 16
- Redis 7
- RabbitMQ 3 (only required if running Celery)
- [`just`](https://just.systems/man/en/packages.html) (optional — used as a task runner)

**1. Clone and create a virtual environment**

```bash
git clone <repo-url>
cd billing
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Create a `.env` file**

```bash
cp .env.example .env
```

Edit `.env` with your local credentials. At minimum:

```env
# Django
DJANGO_SECRET_KEY=any-long-random-string
DEBUG=True

# Postgres
POSTGRES_DB=billing
POSTGRES_USER=billing_user
POSTGRES_PASSWORD=billing_pass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# RabbitMQ (only needed for Celery)
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

If you skip Postgres credentials entirely, the app will fall back to SQLite automatically (fine for quick local testing).

**4. Create the Postgres database**

```bash
psql -U postgres -c "CREATE USER billing_user WITH PASSWORD 'billing_pass';"
psql -U postgres -c "CREATE DATABASE billing OWNER billing_user;"
```

**5. Apply migrations**

```bash
python manage.py migrate
```

**6. Start the development server**

```bash
python manage.py runserver
```

Or with `just`:

```bash
just dev
```

The API will be available at [http://localhost:8000](http://localhost:8000).

**7. Start Celery (in separate terminals)**

Celery is required for scheduled tasks, lifecycle processing, and webhook retries.

Worker:
```bash
celery -A billing worker -l info
```

Beat (scheduler):
```bash
celery -A billing beat -l info
```

Or with `just`:
```bash
just celery-worker
just celery-beat
```

**8. (Optional) Create a superuser for the Django admin**

```bash
python manage.py createsuperuser
```

Admin is available at [http://localhost:8000/admin/](http://localhost:8000/admin/).

**9. (Optional) Set up the Stripe webhook for local development**

Install the [Stripe CLI](https://docs.stripe.com/stripe-cli) and forward webhook events to your local server:

```bash
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe/
```

The CLI will print a webhook signing secret — copy it into `STRIPE_WEBHOOK_SECRET` in your `.env`.

---

## Known Limitations

The system is currently tightly integrated with Stripe identifiers and
object models. While this simplifies development, it introduces
long-term coupling risks.

---

## TODO

### High Priority

#### 1. Decouple From Stripe (Adapter Boundary)

Stripe logic currently exists across services, database models, and business workflows.

**Goal:**
- [ ] Introduce a provider abstraction layer
- [ ] Map Stripe payloads into internal domain objects
- [ ] Prevent Stripe SDK types from leaking into domain logic

**Initial Steps:**
- [ ] Create mapping layer (`stripe -> domain`)
- [ ] Route all Stripe calls through a provider client
- [ ] Gradually refactor services to consume domain models instead of Stripe payloads

---

#### 2. Introduce Lightweight Audit Trail

- [ ] Persist internal domain events for debugging, compliance, and historical analysis

---

#### 3. Improve Reconciliation Observability

- [ ] Add metrics and dashboards around webhook processing and retry behavior

