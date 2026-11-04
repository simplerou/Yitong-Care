from types import SimpleNamespace
from app.services.chat import llm


def test_agents_and_menu_use_separate_models(monkeypatch):
    settings = SimpleNamespace(llm_model='qwen-plus-2025-12-01', menu_llm_model='qwen-plus-2025-07-14')
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    assert llm.get_llm().model == 'qwen-plus-2025-12-01'
    assert llm.get_menu_llm().model == 'qwen-plus-2025-07-14'
    assert settings.llm_model == 'qwen-plus-2025-12-01'


def test_menu_falls_back_when_override_is_empty(monkeypatch):
    settings = SimpleNamespace(llm_model='general', menu_llm_model='')
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    assert llm.get_menu_llm().model == 'general'
