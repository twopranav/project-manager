import logging
from app.api.routes import auth, projects, tasks, comments, users, admin, alert_tasks
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# main fastapi app instance
app = FastAPI(title="Team Task Management API")

# routers to each module (app/api/routes/*)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(alert_tasks.router)

# empty endpoint to redirect root URL to '/docs'
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")