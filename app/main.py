import logging
from pathlib import Path
from app.api.routes import auth, projects, tasks, comments, users, admin
from fastapi import FastAPI
from fastapi.responses import FileResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Team Task Management API")

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(admin.router)

FRONTEND_FILE = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "index.html"
)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_FILE)
