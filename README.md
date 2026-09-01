# Team Task Management API

A RESTful **Team Task Management API** built with **FastAPI**, **PostgreSQL**, **SQLAlchemy**, **Alembic**, and **JWT authentication**.

Create projects, manage members and roles, assign tasks, track progress with status history, and comment on tasks — all behind a clean, documented REST API.

## Features

- JWT-based authentication (register/login)
- Global roles (`admin`, `member`) + project-level roles (`admin`, `manager`, `contributor`, `viewer`)
- Project creation, membership management, and per-project stats
- Task creation, multi-user assignment, and status tracking (`todo → in_progress → in_review → done`, plus `blocked`)
- Full task status history
- Comments with nested replies
- **Async task queue (Celery + Redis)** — background job processing so slow operations (like SMTP sends) don't block API requests
- Background email alerts dispatched through the queue — SMTP sends run on a worker, not the request thread (`POST /alerts/dispatch`, `GET /alerts/dispatch/{task_id}` to poll status)
- Security event logging & abuse detection — unauthorized role changes, repeated 403s, and repeated failed logins are logged to `security_alerts` and rate-limited/deduped via Redis, with email alerts for the actionable ones
- **Load/stress tested** — a Locust load test (`locustfile.py`) simulates concurrent users against the live API; the app has held up well locally at **600 concurrent simulated users**
- Auto-generated Swagger / ReDoc docs

## Tech Stack

FastAPI · PostgreSQL · SQLAlchemy · Alembic · Pydantic · JWT (OAuth2 Bearer) · Celery · Redis · Uvicorn · Docker

## Quickstart

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Create a `.env` file:

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/taskdb
SECRET_KEY=YOUR_SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

REDIS_URL=redis://localhost:6379/0

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=YOUR_SMTP_USERNAME
SMTP_PASSWORD=YOUR_SMTP_PASSWORD
SMTP_USE_TLS=true
SMTP_FROM_EMAIL=alerts@example.com
ALERT_ADMIN_EMAIL=admin@example.com
```

Run migrations and start the server:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for interactive Swagger docs.

### Docker

Alternatively, run the whole stack (API + Postgres + Redis + Celery worker) with Docker:

```bash
docker compose -f docker/docker.compose.yml up -d --build
```

The web container waits for Postgres to come online and runs `alembic upgrade head` automatically before starting Uvicorn.

## Background Jobs (Celery + Redis)

Alert emails are dispatched asynchronously instead of blocking the request thread:

```
POST /alerts/dispatch          → queues an email, returns a task_id (202 Accepted)
GET  /alerts/dispatch/{task_id} → poll status/result of that task
```

Redis also backs request-path rate limiting/dedup — e.g. repeated-403 detection counts denials per actor in a rolling window before firing a single alert, instead of one email per denial.

To run a worker locally (outside Docker):

```bash
celery -A app.core.celery_app.celery_app worker --loglevel=info
```

## Load Testing

A [Locust](https://locust.io/) file is included for stress-testing the API:

```bash
# with the stack running (e.g. via docker compose)
locust -f locustfile.py --host http://localhost:8000
```

Then open **http://localhost:8089** to set concurrent users and spawn rate. Simulated users register, log in, create a project, and hit a mix of read/write endpoints (listing projects, checking stats, creating tasks) to exercise the API under load.

Locally, the app has stayed stable at **600 concurrent simulated users** via Locust.

## Auth Flow

```
POST /auth/register   → create a user (first user becomes global admin)
POST /auth/login       → returns a JWT access token
```

Use the token on protected routes:

```
Authorization: Bearer <token>
```

## Core Endpoints

| Resource | Endpoints |
|---|---|
| Projects | `POST/GET /projects/`, `GET/PATCH/DELETE /projects/{id}` |
| Members | `GET/POST /projects/{id}/members`, `PATCH/DELETE .../members/{user_id}` |
| Tasks | `POST /tasks/`, `GET /tasks/project/{id}`, `GET /tasks/assigned/me`, `PATCH /tasks/{id}` |
| Assignment | `POST/DELETE /tasks/{id}/assign` |
| History | `GET /tasks/{id}/history` |
| Comments | `POST /comments/`, `GET /comments/task/{id}`, `PATCH/DELETE /comments/{id}` |
| Stats | `GET /projects/{id}/stats` |
| Alerts | `POST /alerts/dispatch`, `GET /alerts/dispatch/{task_id}` |

## Testing

139 pytest tests across 11 files cover every route and the business rules layered on top (role hierarchy, admin succession, uniqueness constraints, alerting, etc.). Requires a throwaway Postgres database — see [`tests/README.md`](tests/README.md) for setup and running instructions.

## Project Structure

```text
app/
├── api/routes/       # FastAPI routers (auth, users, projects, tasks, comments, admin, alert_tasks)
├── core/              # Config, security, email, Celery app, Redis client, security-alert logic
├── db/                # Engine/session setup, declarative base
├── models/            # SQLAlchemy models
├── schemas/           # Pydantic request/response schemas
├── scripts/           # One-off scripts (e.g. bootstrap_admin)
└── tasks/             # Celery tasks (background email dispatch)
alembic/                # DB migrations
tests/                  # Pytest suite (see tests/README.md)
docker/                 # Dockerfile, entrypoint, compose file (API + Postgres + Redis)
locustfile.py           # Load test (see Load Testing above)
```