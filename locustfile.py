"""
Load test for the Team Task Management API.
Run with the stack up:
    docker compose -f docker/docker.compose.yml up -d
Then run:
    locust -f locustfile.py --host http://localhost:8000
Open:
    http://localhost:8089
to set concurrent users / spawn rate.
"""

import time
import uuid
from locust import HttpUser, task, between, LoadTestShape

class StepLoadShape(LoadTestShape):
    """
    Set MODE below to choose behavior.
    "step"    -> climbs from STEP_USERS in increments every STEP_TIME
                 seconds, auto-stopping if FAIL_THRESHOLD is crossed.
    "instant" -> jumps straight to INSTANT_USERS at INSTANT_SPAWN_RATE
                 and holds there until you stop it manually or --run-time
                 ends the test.
    """

    MODE = "instant"

    # -- step mode settings --
    STEP_USERS = 25
    STEP_TIME = 60
    SPAWN_RATE = 5
    MAX_USERS = 600
    FAIL_THRESHOLD = 0.03

    # -- instant mode settings --
    INSTANT_USERS = 600
    INSTANT_SPAWN_RATE = 25

    def tick(self):
        if self.MODE == "instant":
            return (self.INSTANT_USERS, self.INSTANT_SPAWN_RATE)
        run_time = self.get_run_time()
        current_step = int(run_time // self.STEP_TIME)
        seconds_into_step = run_time % self.STEP_TIME
        if seconds_into_step > 20 and self.runner is not None:
            fail_ratio = self.runner.stats.total.fail_ratio

            if fail_ratio > self.FAIL_THRESHOLD:
                return None
        user_count = min(
            self.STEP_USERS * (current_step + 1),
            self.MAX_USERS,
        )
        if (
            user_count >= self.MAX_USERS
            and run_time > (self.MAX_USERS / self.STEP_USERS) * self.STEP_TIME
        ):
            return None
        return (user_count, self.SPAWN_RATE)


class ApiUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        """
        Runs once per simulated user.

        Registers, logs in, and creates a project to work against
        for the rest of this user's session.
        """
        unique = uuid.uuid4().hex[:10]
        self.email = f"loadtest-{unique}@test.com"
        self.password = "LoadTest!23"
        # POST /auth/register — JSON body
        self.client.post(
            "/auth/register",
            json={
                "name": f"Load Test {unique}",
                "email": self.email,
                "password": self.password,
            },
            name="/auth/register",
        )
        # POST /auth/login — form-encoded
        resp = self.client.post(
            "/auth/login",
            data={
                "username": self.email,
                "password": self.password,
            },
            name="/auth/login",
        )
        token = resp.json().get("access_token")

        self.headers = {
            "Authorization": f"Bearer {token}"
        }
        # Create a project for this simulated user
        resp = self.client.post(
            "/projects/",
            json={
                "name": f"Load Test Project {unique}"
            },
            headers=self.headers,
            name="/projects/ [create]",
        )
        self.project_id = resp.json().get("id")

    @task(5)
    def list_projects(self):
        self.client.get(
            "/projects/",
            headers=self.headers,
            name="/projects/ [list]",
        )

    @task(3)
    def get_project_stats(self):
        if self.project_id:
            self.client.get(
                f"/projects/{self.project_id}/stats",
                headers=self.headers,
                name="/projects/{id}/stats",
            )

    @task(3)
    def create_task(self):
        if self.project_id:
            self.client.post(
                "/tasks/",
                json={
                    "title": f"Load test task {uuid.uuid4().hex[:8]}",
                    "project_id": self.project_id,
                },
                headers=self.headers,
                name="/tasks/ [create]",
            )

    @task(4)
    def list_project_tasks(self):
        if self.project_id:
            self.client.get(
                f"/tasks/project/{self.project_id}",
                headers=self.headers,
                name="/tasks/project/{id}",
            )

    @task(2)
    def get_my_tasks(self):
        self.client.get(
            "/tasks/assigned/me",
            headers=self.headers,
            name="/tasks/assigned/me",
        )

    @task(1)
    def get_me(self):
        self.client.get(
            "/users/me",
            headers=self.headers,
            name="/users/me",
        )


class AlertDispatchUser(HttpUser):
    """
    Reproduces the submit-then-poll pattern used by loader.py.
    This stresses the async alert pipeline:
        FastAPI -> Redis -> Celery -> SMTP
    """
    weight = 1
    wait_time = between(1, 3)
    POLL_INTERVAL = 0.25
    POLL_TIMEOUT = 30.0

    def on_start(self):
        """
        Register and log in this simulated user.
        This class needs its own token because
        /alerts/dispatch is authenticated.
        """
        unique = uuid.uuid4().hex[:10]
        email = f"loadtest-alert-{unique}@test.com"
        password = "LoadTest!23"
        self.client.post(
            "/auth/register",
            json={
                "name": f"Alert User {unique}",
                "email": email,
                "password": password,
            },
            name="/auth/register",
        )
        resp = self.client.post(
            "/auth/login",
            data={
                "username": email,
                "password": password,
            },
            name="/auth/login",
        )
        token = resp.json().get("access_token")

        self.headers = {
            "Authorization": f"Bearer {token}"
        }

    @task
    def dispatch_and_await_alert(self):
        payload = {
            "subject": f"[Load Test] alert #{uuid.uuid4().hex[:8]}",
            "body": "Synthetic load-test alert generated by locustfile.py",
            "to": None,
        }
        # Start measuring the complete submit -> completion process
        start = time.monotonic()
        with self.client.post(
            "/alerts/dispatch",
            json=payload,
            headers=self.headers,
            name="/alerts/dispatch [submit]",
            catch_response=True,
        ) as resp:
            if resp.status_code != 202:
                resp.failure(
                    f"unexpected status {resp.status_code}"
                )
                return
            task_id = resp.json()["task_id"]
        deadline = start + self.POLL_TIMEOUT
        with self.client.get(
            f"/alerts/dispatch/{task_id}",
            headers=self.headers,
            name="/alerts/dispatch/{id} [poll-to-completion]",
            catch_response=True,
        ) as resp:
            status = resp.json().get("status")
            while status not in ("SUCCESS", "FAILURE"):
                if time.monotonic() >= deadline:
                    resp.failure(
                        f"timed out after {self.POLL_TIMEOUT}s, "
                        f"last status={status}"
                    )
                    return
                time.sleep(self.POLL_INTERVAL)
                poll = self.client.get(
                    f"/alerts/dispatch/{task_id}",
                    headers=self.headers,
                    name="/alerts/dispatch/{id} [poll-to-completion]",
                )
                status = poll.json().get("status")
            if status == "FAILURE":
                resp.failure(
                    "alert task ended in FAILURE"
                )
            # SUCCESS falls through and Locust records the request as successful.