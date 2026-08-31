# Talks to the /alerts/dispatch endpoints over HTTP.

from __future__ import annotations
import itertools
import sys
import threading
import time
import requests

API_BASE = "http://127.0.0.1:8000"
POLL_INTERVAL = 0.15       # seconds between status checks
SLOW_THRESHOLD = 1.0       # seconds before we switch into "please wait" mode
ANIMATION_FRAME_DELAY = 0.4

def _run_animation(stop_event: threading.Event) -> None:
    """Loops '.', '..', '...' on the same terminal line until stop_event is set."""
    frames = itertools.cycle([".", "..", "..."])
    while not stop_event.is_set():
        frame = next(frames)
        sys.stdout.write(f"\rplease wait while we service your request{frame}   ")
        sys.stdout.flush()
        stop_event.wait(ANIMATION_FRAME_DELAY)

def _clear_line() -> None:
    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()

def dispatch_and_wait(subject: str, body: str, to: str | None = None) -> dict:
    start = time.monotonic()
    submit_resp = requests.post(
        f"{API_BASE}/alerts/dispatch",
        json={"subject": subject, "body": body, "to": to},
    )
    submit_resp.raise_for_status()
    task_id = submit_resp.json()["task_id"]
    stop_event = threading.Event()
    anim_thread: threading.Thread | None = None
    result: dict | None = None
    while True:
        status_resp = requests.get(f"{API_BASE}/alerts/dispatch/{task_id}")
        status_resp.raise_for_status()
        data = status_resp.json()
        if data["status"] in ("SUCCESS", "FAILURE"):
            result = data
            break
        elapsed = time.monotonic() - start
        if elapsed > SLOW_THRESHOLD and anim_thread is None:
            anim_thread = threading.Thread(target=_run_animation, args=(stop_event,), daemon=True)
            anim_thread.start()
        time.sleep(POLL_INTERVAL)
    if anim_thread is not None:
        stop_event.set()
        anim_thread.join()
        _clear_line()
    print(f"Result: {result}")
    return result  # type: ignore[return-value]


if __name__ == "__main__":
    dispatch_and_wait(
        subject="Test Alert",
        body="This is a test alert dispatched from client.py",
    )