from app.config import load_config


def test_individual_variant() -> None:
    config = load_config()
    assert config.scenario_id == "car_wash"
    assert config.scenario_name == "Автомойка"
    assert config.language == "ru"
    assert config.keywords == ["мойка", "кузов", "салон", "запись"]


def test_env_overrides_prompt_and_preprocessing(monkeypatch) -> None:
    from app.config import load_config

    base = load_config()
    assert base.initial_prompt and base.preprocess_audio is True

    monkeypatch.setenv("WHISPER_PROMPT", "")
    monkeypatch.setenv("AUDIO_PREPROCESS", "0")
    monkeypatch.setenv("WHISPER_MODEL", "small")
    changed = load_config()
    assert changed.initial_prompt == "" and changed.preprocess_audio is False
    assert changed.model == "small" and changed.model_display_name == "whisper-small"
