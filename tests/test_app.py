from http.client import IncompleteRead
from io import BytesIO
import json
import os
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from review_system.environment import PROJECT_ROOT
from review_system.workflow import MAX_INPUT_CHARS


def chat_response(content):
    return BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def test_interrupted_review_preserves_current_results_across_reruns():
    # Mock the environment loader and transport so no real .env or API is used.
    env = {"REVIEW_PROVIDER": "qwen", "QWEN_API_KEY": "synthetic-placeholder"}
    replies = [chat_response(content) for content in ["Analysis", "Critique", "Verdict", "New analysis"]]
    replies.append(IncompleteRead(b"synthetic-private-response"))
    with patch.dict(os.environ, env, clear=True), patch("review_system.environment.load_project_env"), patch(
        "review_system.clients.urlopen", side_effect=replies,
    ) as send:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        assert app.text_area[0].max_chars == MAX_INPUT_CHARS
        app.text_area[0].set_value("Synthetic input")
        app.button[0].click().run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["Analysis", "Critique", "Verdict"]

        app.button[0].click().run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["New analysis"]
        assert len(app.error) == 1
        assert app.error[0].value == "Critic failed: Provider connection was interrupted."
        assert [item.content for item in app.session_state["review_result"]] == ["New analysis"]
        assert send.call_count == 5

        app.run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["New analysis"]
        assert len(app.error) == 1
        assert send.call_count == 5

        app.text_area[0].set_value(" ")
        app.button[0].click().run()
        assert not app.exception
        assert not app.markdown
        assert len(app.error) == 1
        assert send.call_count == 5


def test_callback_error_preserves_response_for_later_rerun():
    env = {"REVIEW_PROVIDER": "qwen", "QWEN_API_KEY": "synthetic-placeholder"}
    with patch.dict(os.environ, env, clear=True), patch("review_system.environment.load_project_env"), patch(
        "review_system.clients.urlopen", return_value=chat_response("Analysis"),
    ) as send:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
        app.text_area[0].set_value("Synthetic input")
        with patch("streamlit.markdown", side_effect=RuntimeError("synthetic-private-detail")):
            app.button[0].click().run()
        assert not app.exception
        assert len(app.error) == 1
        assert app.error[0].value == "Analyst failed: Response callback failed."
        assert [item.content for item in app.session_state["review_result"]] == ["Analysis"]
        assert send.call_count == 1

        app.run()
        assert not app.exception
        assert [item.value for item in app.markdown] == ["Analysis"]
        assert len(app.error) == 1
        assert send.call_count == 1
