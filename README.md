Team Task Management System

A RESTful Team Task Management API built with **Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Pydantic, and JWT authentication**.

The API allows users to create and manage projects, manage project members and roles, create and assign tasks, track task progress, add comments, and view basic project statistics.

## Features

* JWT-based authentication
* User registration and login
* Role-based authorization
* Project creation and management
* Project member management
* Project-level roles
* Task creation and management
* Assign multiple team members to tasks
* Task status and progress tracking
* Task status history
* Comments and nested replies
* Project statistics
* PostgreSQL database
* SQLAlchemy ORM
* Alembic database migrations
* Pydantic request/response validation
* FastAPI Swagger/OpenAPI documentation
* End-to-end PowerShell API smoke tests

## Technology Stack

| Technology           | Purpose                     |
| -------------------- | --------------------------- |
| Python               | Programming language        |
| FastAPI              | REST API framework          |
| PostgreSQL           | Relational database         |
| SQLAlchemy           | ORM and database access     |
| Alembic              | Database migrations         |
| Pydantic             | Request/response validation |
| JWT                  | Authentication              |
| OAuth2 Bearer Tokens | API authorization           |
| Uvicorn              | ASGI server                 |

## Project Structure

```text
project-manager/
├── alembic/
│   ├── versions/
│   └── env.py
├── app/
│   ├── api/
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── comments.py
│   │       ├── projects.py
│   │       ├── tasks.py
│   │       └── users.py
│   ├── core/
│   │   ├── config.py
│   │   └── security.py
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   ├── schemas/
│   └── main.py
├── testers/
│   └── test-api.ps1
├── .env
├── .gitignore
├── alembic.ini
├── requirements.txt
└── README.md
```

## Requirements

Install the following before running the project:

* Python 3.10+
* PostgreSQL
* Git

## Installation

### Clone the Repository

```bash
git clone https://github.com/twopranav/project-manager.git
cd project-manager
```

### Create a Virtual Environment

#### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Database Setup

Create a PostgreSQL database.

For example:

```sql
CREATE DATABASE taskdb;
```

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/taskdb
SECRET_KEY=YOUR_SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Replace:

* `YOUR_PASSWORD` with your PostgreSQL password
* `YOUR_SECRET_KEY` with a long random secret

### Important

**Do not commit `.env` to Git.**

Your `.gitignore` should contain:

```gitignore
.env
.venv/
__pycache__/
*.pyc
```

## Run Database Migrations

From the project root:

```powershell
alembic upgrade head
```

This creates the database tables required by the application.

To check the current migration:

```powershell
alembic current
```

## Run the API

Start the FastAPI application:

```powershell
uvicorn app.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

## API Documentation

FastAPI automatically provides interactive API documentation.

### Swagger UI

```text
http://127.0.0.1:8000/docs
```

### ReDoc

```text
http://127.0.0.1:8000/redoc
```

Swagger can be used to obtain a JWT token and test authenticated endpoints.

## Authentication

### Register

```http
POST /auth/register
```

Example request:

```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "password123"
}
```

### Login

```http
POST /auth/login
```

The login endpoint uses OAuth2 password-form fields.

Use:

```text
username = your email
password = your password
```

A successful login returns an access token:

```json
{
  "access_token": "YOUR_JWT_TOKEN",
  "token_type": "bearer"
}
```

Use the returned token in authenticated requests:

```http
Authorization: Bearer YOUR_JWT_TOKEN
```

## User Roles

The application uses both global roles and project-level roles.

### Global Roles

| Role      | Purpose                        |
| --------- | ------------------------------ |
| `admin`   | Site-wide administrator        |
| `manager` | Regular global management role |
| `member`  | Standard user                  |

The first registered user is automatically assigned the global `admin` role. Subsequent users are registered as `member` users.

### Project Roles

| Role          | Purpose                                          |
| ------------- | ------------------------------------------------ |
| `admin`       | Full project administration                      |
| `manager`     | Manage projects and higher-level task operations |
| `contributor` | Create tasks and update task status              |
| `viewer`      | Read-only project access                         |

The user who creates a project automatically becomes that project's `admin`.

A project must always retain at least one project administrator.

## Main API Endpoints

### Authentication

```text
POST   /auth/register
POST   /auth/login
```

### Users

```text
GET    /users/me
PATCH  /users/me
```

### Projects

```text
POST   /projects/
GET    /projects/
GET    /projects/{project_id}
PATCH  /projects/{project_id}
DELETE /projects/{project_id}
```

### Project Members

```text
GET    /projects/{project_id}/members
POST   /projects/{project_id}/members
PATCH  /projects/{project_id}/members/{user_id}
DELETE /projects/{project_id}/members/{user_id}
DELETE /projects/{project_id}/leave
```

### Project Statistics

```text
GET /projects/{project_id}/stats
```

The statistics endpoint provides:

* Total task count
* Task counts grouped by status
* Number of overdue incomplete tasks

### Tasks

```text
POST   /tasks/
GET    /tasks/project/{project_id}
GET    /tasks/assigned/me
GET    /tasks/{task_id}
PATCH  /tasks/{task_id}
```

### Task Assignment

```text
POST   /tasks/{task_id}/assign
DELETE /tasks/{task_id}/assign/{user_id}
```

Tasks can have multiple assigned team members.

### Task Status History

```text
GET /tasks/{task_id}/history
```

Task status changes are recorded in a history table so progress can be tracked over time.

### Comments

```text
POST   /comments/
GET    /comments/task/{task_id}
PATCH  /comments/{comment_id}
DELETE /comments/{comment_id}
```

Comments support nested replies through parent comments.

## Task Statuses

Tasks support the following statuses:

```text
todo
in_progress
in_review
done
blocked
```

Contributors can update task status, while manager-level users can update additional task information such as title, description, priority, and due date.

## Task Priorities

Tasks support priority levels defined by the application.

Use the Swagger documentation at:

```text
http://127.0.0.1:8000/docs
```

for the currently available enum values.

## Testing

The repository contains an end-to-end PowerShell smoke test:

```text
testers/test-api.ps1
```

Start the API first:

```powershell
uvicorn app.main:app --reload
```

Then run:

```powershell
.\testers\test-api.ps1
```

If PowerShell execution policy blocks the script:

```powershell
powershell -ExecutionPolicy Bypass -File .\testers\test-api.ps1
```

The test suite covers major application flows including:

* User registration and authentication
* Project creation
* Role and authorization checks
* Project membership
* Task creation
* Task assignment
* Task updates
* Comments
* Task status history
* Project statistics

## Database Verification

The project uses PostgreSQL through the `DATABASE_URL` configured in `.env`.

The database can be verified directly through PostgreSQL or pgAdmin.

For example:

```sql
SELECT current_database();
```

Expected result:

```text
taskdb
```

Application tables can also be inspected:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

## Database Migrations

Create a new migration after changing SQLAlchemy models:

```powershell
alembic revision --autogenerate -m "describe your change"
```

Apply migrations:

```powershell
alembic upgrade head
```

Rollback the most recent migration:

```powershell
alembic downgrade -1
```

## Development Workflow

A typical development workflow is:

```text
1. Activate virtual environment
2. Start PostgreSQL
3. Configure .env
4. Run Alembic migrations
5. Start FastAPI
6. Test endpoints using Swagger or the PowerShell test suite
7. Make model/schema changes
8. Generate and apply Alembic migrations
```

## Security Notes

* Passwords are stored as hashes rather than plaintext passwords.
* API authentication uses signed JWT access tokens.
* Protected routes require bearer authentication.
* Project permissions are enforced using project-level roles.
* `.env` should not be committed to source control.
* Production deployments should use a strong randomly generated `SECRET_KEY`.
* Production deployments should use HTTPS.

## Assignment Coverage

This project satisfies the requested Team Task Management API requirements:

| Requirement                  | Implementation                 |
| ---------------------------- | ------------------------------ |
| Create projects              | Project API                    |
| Assign tasks to team members | Task assignment API            |
| Update task progress         | Task status + status history   |
| Add comments                 | Comment API                    |
| View project statistics      | Project statistics endpoint    |
| Decide user roles            | Global and project-level roles |
| Python                       | Python                         |
| FastAPI                      | FastAPI                        |
| PostgreSQL                   | PostgreSQL                     |
| SQLAlchemy                   | SQLAlchemy ORM                 |
| Alembic                      | Alembic migrations             |
| Pydantic                     | Pydantic schemas               |
| JWT authentication           | JWT bearer authentication      |

## License

This project was created as a Team Task Management API project.
