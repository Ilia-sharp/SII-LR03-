import io
import os
import wave

os.environ["SII_LR03_SKIP_MODEL"] = "1"

from fastapi.testclient import TestClient

from app.asr import Segment
from app.main import app


class DummyTranscriber:
    def transcribe(self, wav_path: str):
        return "Нужна мойка кузова", [Segment(start=0.0, end=1.2, text="Нужна мойка кузова")]


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_file() -> None:
    with TestClient(app) as client:
        response = client.post("/transcribe", files={"file": ("empty.wav", b"", "audio/wav")})
    assert response.status_code == 400
    assert "пустой" in response.json()["detail"].lower()


def test_unsupported_extension() -> None:
    with TestClient(app) as client:
        response = client.post("/transcribe", files={"file": ("note.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_too_long_file() -> None:
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000 * 61)
    audio.seek(0)
    with TestClient(app) as client:
        response = client.post(
            "/transcribe",
            files={"file": ("long.wav", audio, "audio/wav")},
        )
    assert response.status_code == 413
    assert "превышает лимит" in response.json()["detail"]


def test_transcribe_contract() -> None:
    with TestClient(app) as client:
        client.app.state.transcriber = DummyTranscriber()
        sample = os.path.join(os.path.dirname(__file__), "..", "samples", "02_body_wash.wav")
        with open(sample, "rb") as fh:
            response = client.post("/transcribe", files={"file": ("sample.wav", fh, "audio/wav")})
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_id"] == "car_wash"
    assert body["scenario_name"] == "Автомойка"
    assert body["language"] == "ru"
    assert body["model"] == "whisper-base"
    assert {item["keyword"] for item in body["keywords_found"]} == {"мойка", "кузов"}
    assert body["segments"][0]["text"] == "Нужна мойка кузова"


def test_scenario_endpoint() -> None:
    with TestClient(app) as client:
        body = client.get("/scenario").json()
    assert body["keywords"] == ["мойка", "кузов", "салон", "запись"]
    assert body["scenario_id"] == "car_wash"


def test_transcribe_without_model_returns_503() -> None:
    sample = os.path.join(os.path.dirname(__file__), "..", "samples", "02_body_wash.wav")
    with TestClient(app) as client:
        client.app.state.transcriber = None
        with open(sample, "rb") as fh:
            response = client.post("/transcribe", files={"file": ("s.wav", fh, "audio/wav")})
    assert response.status_code == 503


def test_transcriber_crash_returns_json_500() -> None:
    class Broken:
        def transcribe(self, wav_path: str):
            raise RuntimeError("boom")

    sample = os.path.join(os.path.dirname(__file__), "..", "samples", "02_body_wash.wav")
    with TestClient(app) as client:
        client.app.state.transcriber = Broken()
        with open(sample, "rb") as fh:
            response = client.post("/transcribe", files={"file": ("s.wav", fh, "audio/wav")})
    assert response.status_code == 500
    assert "detail" in response.json()


def test_fake_audio_with_wav_extension_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.post("/transcribe", files={"file": ("fake.wav", b"not audio at all", "audio/wav")})
    assert response.status_code == 415


def test_oversized_upload_returns_413() -> None:
    with TestClient(app) as client:
        client.app.state.decoder.max_upload_bytes = 1024
        response = client.post("/transcribe", files={"file": ("big.wav", b"\x00" * 4096, "audio/wav")})
    assert response.status_code == 413
    assert "слишком большой" in response.json()["detail"]


def test_ready_endpoint() -> None:
    with TestClient(app) as client:
        body = client.get("/ready").json()
    assert body["model_loaded"] is False  # в тестах модель не грузится


SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "..", "samples", "02_body_wash.wav")


class ProgressDummy:
    """Транскрайбер нового формата: сообщает прогресс и возвращает сегмент с отступом тишины."""

    def transcribe(self, wav_path: str, on_progress=None):
        from app.asr import Segment

        if on_progress:
            on_progress(0.5)
            on_progress(1.0)
        return "нужна мойка кузова", [Segment(0.5, 1.5, "нужна мойка кузова")]


def test_progress_unknown_job_is_waiting() -> None:
    with TestClient(app) as client:
        body = client.get("/progress/does-not-exist-123").json()
    assert body["stage"] == "waiting" and body["percent"] == 0 and body["done"] is False


def test_progress_reaches_100_and_timestamps_ignore_padding() -> None:
    job = "job-test-1234567"
    with TestClient(app) as client:
        client.app.state.transcriber = ProgressDummy()
        with open(SAMPLE_PATH, "rb") as fh:
            response = client.post(
                "/transcribe",
                files={"file": ("s.wav", fh, "audio/wav")},
                headers={"X-Job-Id": job},
            )
        progress = client.get(f"/progress/{job}").json()
        pad = client.app.state.decoder.pad_seconds
    assert response.status_code == 200
    assert progress["percent"] == 100 and progress["done"] is True and progress["stage"] == "done"
    # тишина, добавленная по краям при подготовке звука, вычтена из таймкодов
    segment = response.json()["segments"][0]
    assert segment["start"] == max(0.0, 0.5 - pad)
    assert segment["end"] == 1.5 - pad


def test_progress_marks_error_and_bad_job_id_is_ignored() -> None:
    job = "job-test-error-1"
    with TestClient(app) as client:
        client.post(
            "/transcribe",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers={"X-Job-Id": job},
        )
        error_state = client.get(f"/progress/{job}").json()
        # некорректный идентификатор не должен ломать запрос
        response = client.post(
            "/transcribe",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers={"X-Job-Id": "../../etc/passwd"},
        )
    assert error_state["stage"] == "error" and error_state["done"] is True
    assert response.status_code == 415


def test_preprocessing_adds_padding_and_keeps_audio_decodable() -> None:
    import subprocess
    from pathlib import Path

    from app.audio import AudioDecoder

    def duration(path: Path) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())

    source = Path(SAMPLE_PATH)
    plain = AudioDecoder(60, [".wav"], preprocess=False)
    prepared = AudioDecoder(60, [".wav"], preprocess=True)
    wav_plain, wav_prepared = plain.decode_to_wav(source), prepared.decode_to_wav(source)
    try:
        assert abs(duration(wav_prepared) - duration(wav_plain) - 2 * prepared.pad_seconds) < 0.1
        assert plain.pad_seconds == 0.0
    finally:
        wav_plain.unlink(missing_ok=True)
        wav_prepared.unlink(missing_ok=True)
