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
- Auto-generated Swagger / ReDoc docs

## Tech Stack

FastAPI · PostgreSQL · SQLAlchemy · Alembic · Pydantic · JWT (OAuth2 Bearer) · Uvicorn

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
```

Run migrations and start the server:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for interactive Swagger docs.

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

## Testing

Refer to the README.md file within the `tests` file