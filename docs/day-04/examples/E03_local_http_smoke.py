"""Real loopback HTTP smoke test with injected fake models; no key or paid call.

Run from mvp: PYTHONPATH=. .venv/bin/python docs/day-04/examples/E03_local_http_smoke.py
"""

import asyncio
from contextlib import asynccontextmanager
import socket

import httpx
import uvicorn

from review_system.api import create_app
from review_system.config import Settings
from review_system.fakes import DemoClient


class WaitingCritic(DemoClient):
    async def complete(self, *, model, messages):
        if model == "c":
            await asyncio.Event().wait()
        return await super().complete(model=model, messages=messages)


async def serve_and_check(*, timeout=False):
    @asynccontextmanager
    async def resources():
        yield "fake", WaitingCritic() if timeout else DemoClient(), Settings(
            "fake", "https://example.invalid", "", "m", "a", "c", "j",
            model_timeout_seconds=0.02 if timeout else 60,
        )

    app = create_app(resources_factory=resources)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Server exited before startup.")
                await asyncio.sleep(0.01)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False) as http:
                health = await http.get("/healthz")
                assert health.status_code == 200 and health.json()["execution_mode"] == "fake"
                response = await http.post("/api/v1/reviews", json={
                    "request_id": "loopback-demo", "original_input": "仅用内存保存历史。",
                })
                body = response.json()
                if timeout:
                    assert response.status_code == 504
                    assert body["error"]["code"] == "model_timeout"
                    assert len(body["responses"]) == 1 and body["final_review"] is None
                    print("504 model_timeout; Analyst preserved; no final report")
                else:
                    assert response.status_code == 201
                    assert len(body["responses"]) == 3 and body["status"] == "succeeded"
                    print("201 succeeded; three responses; execution_mode=fake")
                    invalid = await http.post("/api/v1/reviews", json={
                        "request_id": "invalid", "original_input": " ",
                    })
                    assert invalid.status_code == 422
                    assert invalid.json()["error"]["code"] == "invalid_request"
                    print("422 invalid_request; no review_id or model results")
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(5):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            listener.close()
    assert app.state.service.active_count == app.state.service.task_count == 0


async def main():
    await serve_and_check()
    await serve_and_check(timeout=True)
    print("Loopback servers stopped; review tasks collected.")


if __name__ == "__main__":
    asyncio.run(main())
