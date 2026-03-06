from types import SimpleNamespace

from receipt_processor import llm_agent
from receipt_processor.schemas import LLMParseResult


def _install_agent_spy(monkeypatch):
    captured: dict = {}

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return object()

    class DummyRunResult:
        def final_output_as(self, *args, **kwargs):
            return LLMParseResult.model_validate({"receipt": {}})

    monkeypatch.setattr(llm_agent, "Agent", fake_agent)
    monkeypatch.setattr(llm_agent.Runner, "run_sync", lambda *args, **kwargs: DummyRunResult())
    return captured


def test_parse_receipt_with_llm_omits_sampling_params_for_o3(monkeypatch) -> None:
    captured = _install_agent_spy(monkeypatch)
    settings = SimpleNamespace(openai_api_key="test-key", openai_base_url=None, parser_model="o3")

    llm_agent.parse_receipt_with_llm("K-Market", settings=settings, debug=False)

    assert "model_settings" not in captured


def test_parse_receipt_with_llm_uses_deterministic_sampling_for_gpt4_1(monkeypatch) -> None:
    captured = _install_agent_spy(monkeypatch)
    settings = SimpleNamespace(openai_api_key="test-key", openai_base_url=None, parser_model="gpt-4.1")

    llm_agent.parse_receipt_with_llm("K-Market", settings=settings, debug=False)

    assert "model_settings" in captured
    model_settings = captured["model_settings"]
    assert isinstance(model_settings, llm_agent.ModelSettings)
    assert model_settings.temperature == 0
    assert model_settings.top_p == 1.0
