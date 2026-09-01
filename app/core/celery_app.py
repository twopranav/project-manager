# Celery entry point. gevent.monkey.patch_all() MUST run before anything
# else imports socket/ssl/threading — that's why it's the very first thing
# in this file, above even the stdlib-touching Celery import. On Windows,
# the default "prefork" pool relies on os.fork(), which doesn't exist —
# workers either crash on boot or silently hang. gevent sidesteps that
# entirely since it's a cooperative, single-process pool, which also happens
# to be the right tool for I/O-bound work like outbound SMTP/webhook calls.

import os
if os.environ.get("IS_CELERY_WORKER") == "1":
    import gevent.monkey
    gevent.monkey.patch_all()
from celery import Celery
from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "team_task_mgmt",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.alerts"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Ack the task only after it finishes, not the moment it's picked up.
    # If a worker dies mid-send, the task goes back on the queue instead
    # of silently vanishing.
    task_acks_late=True,

    # Fetch one task at a time per worker slot instead of grabbing a batch
    # up front. Prevents one worker from hoarding a burst of alert tasks
    # while other workers sit idle.
    worker_prefetch_multiplier=1,

    # Keep result rows around long enough for the client's polling loop to
    # read them, without letting Redis accumulate them forever.
    result_expires=3600,
)