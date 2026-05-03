import llm_client


def test_request_timeout_bounds_env(monkeypatch):
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "1")
    assert llm_client._request_timeout_seconds() == 3.0

    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "120")
    assert llm_client._request_timeout_seconds() == 45.0

    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "bad")
    assert llm_client._request_timeout_seconds() == 14.0


def test_openai_client_sets_timeout_and_disables_retries(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_client, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "9")

    client = llm_client._openai_client("https://example.test/v1", "key")

    assert isinstance(client, FakeOpenAI)
    assert captured["base_url"] == "https://example.test/v1"
    assert captured["api_key"] == "key"
    assert captured["timeout"] == 9.0
    assert captured["max_retries"] == 0
