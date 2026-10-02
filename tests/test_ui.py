from fastapi.testclient import TestClient

from app.main import app


def test_ui_homepage() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Аудио → текст → ключевые слова" in response.text


def test_ui_static_assets() -> None:
    with TestClient(app) as client:
        response = client.get("/static/style.css")
        assert response.status_code == 200
        assert "--accent" in response.text
