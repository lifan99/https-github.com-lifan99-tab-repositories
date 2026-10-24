"""在同一本机端口先后启动两个 fake API 进程，验证重启后的请求处理和资源清理。"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BODY = {"request_id": "restart-demo", "original_input": "仅用内存保存历史。", "review_mode": "logic"}


def one_process(port):
    """启动一轮离线服务，验证健康和审核接口，并在所有退出路径回收进程与管道。"""
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "review_system.api:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--workers", "1", "--log-level", "error"],
        cwd=ROOT, env={**os.environ, "REVIEW_EXECUTION_MODE": "fake"},
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False) as http:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Fake API process exited before startup.")
                try:
                    health = http.get("/healthz")
                    if health.status_code == 200:
                        assert health.json()["execution_mode"] == "fake"
                        break
                except httpx.RequestError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Fake API startup deadline exceeded.")
                time.sleep(0.05)
            response = http.post("/api/v1/reviews", json=BODY)
            assert response.status_code == 201
            result = response.json()
            assert result["status"] == "succeeded" and len(result["responses"]) == 3
            assert result["execution_mode"] == "fake"
            # 当前系统没有历史查询端点；重启演示不代表持久化或跨进程幂等。
            assert http.get(f"/api/v1/reviews/{result['review_id']}").status_code == 404
            return process.pid, result["review_id"]
    # 断言或连接失败时也先尝试正常终止，超时后强制结束，避免残留服务进程。
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stderr is not None:
            process.stderr.close()


def main():
    """复用同一本机端口先后运行两轮，验证同一请求标识在重启后产生新审核。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    first_pid, first_id = one_process(port)
    second_pid, second_id = one_process(port)
    assert first_pid != second_pid and first_id != second_id
    print("Two distinct API processes started and stopped on the same loopback port.")
    print("Same request_id accepted again after restart; new review_id and three model stages.")
    print("No history endpoint; no persistent idempotency claim.")


if __name__ == "__main__":
    main()
