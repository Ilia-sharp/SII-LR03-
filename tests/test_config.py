from app.config import load_config


def test_individual_variant() -> None:
    config = load_config()
    assert config.scenario_id == "car_wash"
    assert config.scenario_name == "Автомойка"
    assert config.language == "ru"
    assert config.keywords == ["мойка", "кузов", "салон", "запись"]
