"""通过 Streamlit AppTest、本机 HTTP、API 和真实工作流验证界面链路，模型使用离线替身。

在 mvp 目录运行：PYTHONPATH=. .venv/bin/python examples/ui/E01_ui_http_smoke.py。
"""

import asyncio
from contextlib import asynccontextmanager
import socket
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import uvicorn

from review_system.api import create_app
from review_system.clients import LLMError
from review_system.config import Settings
from review_system.environment import PROJECT_ROOT
from review_system.fakes import DemoClient


class DemoFailureClient(DemoClient):
    """首轮审核成功，第二轮在第五次调用即 Critic 阶段失败，检查旧报告清除。"""
    def __init__(self):
        self.calls = 0

    async def complete(self, *, model, messages):
        self.calls += 1
        if self.calls == 5:
            raise LLMError("Synthetic failure; do not expose this detail.")
        return await super().complete(model=model, messages=messages)


async def main():
    """启动真实本机 API，在工作线程中运行同步页面测试，并最终收集服务任务。"""
    model = DemoFailureClient()

    @asynccontextmanager
    async def resources():
        yield "fake", model, Settings("fake", "https://example.invalid", "", "m", "a", "c", "j")

    api = create_app(resources_factory=resources)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api, log_level="error", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))

    def run_ui():
        """通过页面操作验证成功、会话恢复及第二次审核失败时的部分结果展示。"""
        with patch.dict("os.environ", {"REVIEW_API_BASE_URL": f"http://127.0.0.1:{port}"}, clear=True), patch("review_system.environment.load_project_env"):
            ui = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=10).run()
            ui.text_area[0].set_value("仅用内存保存记录，重启后历史仍在。")
            ui.button[0].click().run()
            assert not ui.exception and not ui.error
            assert ui.metric[0].value == "insufficient_evidence"
            assert "FAKE" in ui.warning[0].value
            assert len(ui.markdown) == 3 and model.calls == 3
            first_id = ui.session_state["review_record"].review_id
            ui.run()
            assert ui.session_state["review_record"].review_id == first_id and model.calls == 3
            print("UI -> HTTP -> API -> A/C/J: success; fake badge; rerun sends no request")
            ui.button[0].click().run()
            assert not ui.exception and len(ui.error) == 1
            assert "model_error" in ui.error[0].value
            assert len(ui.markdown) == 1 and not ui.metric
            assert ui.session_state["review_record"].review_id != first_id
            assert model.calls == 5
            ui.run()
            assert len(ui.markdown) == 1 and model.calls == 5
            print("UI -> HTTP -> API -> Critic failure: partial result preserved; old report cleared")

    try:
        async with asyncio.timeout(30):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Server exited before startup.")
                await asyncio.sleep(0.01)
            # AppTest 和页面 HTTP 请求是同步操作；放到线程执行，让事件循环继续处理 API 请求。
            await asyncio.to_thread(run_ui)
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
    assert api.state.service.active_count == api.state.service.task_count == 0
    print("Local API stopped; all owned review tasks collected.")


if __name__ == "__main__":
    asyncio.run(main())
