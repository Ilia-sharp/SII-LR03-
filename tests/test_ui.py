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


def test_assets_are_versioned_and_not_stuck_in_cache() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        assert "/static/style.css?v=" in page.text and "/static/app.js?v=" in page.text
        assert page.headers["cache-control"] == "no-store"
        css = client.get("/static/style.css")
        assert css.headers["cache-control"] == "no-cache"
        assert "UI v2" in css.text  # по этой метке видно, что отдаётся новый CSS


def test_every_svg_has_explicit_size() -> None:
    import re
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
    svgs = re.findall(r"<svg\b[^>]*>", html)
    assert svgs and all("width=" in tag and "height=" in tag for tag in svgs)
