from io import BytesIO
import json
from unittest.mock import patch
from review_system.clients import OpenAICompatibleClient
from review_system.config import Settings

def test_request_contract():
    settings = Settings("qwen", "https://example.invalid/v1", "synthetic-key", "m", "m", "m", "m", 12)
    messages = [{"role": "user", "content": "U"}]
    response = BytesIO(b'{"choices":[{"message":{"content":"OK"}}]}')
    with patch("review_system.clients.urlopen", return_value=response) as send:
        assert OpenAICompatibleClient(settings).complete(model="chosen", messages=messages) == "OK"
    request = send.call_args.args[0]
    assert request.full_url == "https://example.invalid/v1/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer synthetic-key"
    assert json.loads(request.data) == {"model": "chosen", "messages": messages, "stream": False}
    assert send.call_args.kwargs["timeout"] == 12
