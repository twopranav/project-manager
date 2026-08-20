from fastapi import FastAPI
from app.api.routes import auth, projects, tasks, comments

app = FastAPI(title="Team Task Management API")

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(comments.router)