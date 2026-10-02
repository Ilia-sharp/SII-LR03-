from __future__ import annotations

import inspect
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Header, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.asr import Segment, WhisperTranscriber
from app.audio import (
    AudioDecoder,
    AudioTooLongError,
    EmptyAudioError,
    FileTooLargeError,
    UnsupportedAudioError,
)
from app.config import load_config
from app.keywords import find_keywords
from app.schemas import KeywordResponse, SegmentResponse, TranscriptionResponse


config = load_config()
logger = logging.getLogger("uvicorn.error")


STAGE_LABELS = {
    "waiting": "Ожидание",
    "decode": "Подготовка аудио",
    "transcribe": "Распознавание речи",
    "keywords": "Поиск ключевых слов",
    "done": "Готово",
    "error": "Ошибка",
}
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ProgressTracker:
    """Прогресс обработки по идентификатору задачи (его присылает веб-интерфейс)."""

    def __init__(self, ttl: float = 600.0, max_items: int = 200) -> None:
        self._items: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max_items = max_items

    def set(self, job_id: str | None, stage: str, percent: float) -> None:
        if not job_id:
            return
        now = time.time()
        with self._lock:
            self._items[job_id] = {
                "stage": stage,
                "label": STAGE_LABELS.get(stage, stage),
                "percent": round(max(0.0, min(100.0, percent)), 1),
                "done": stage in {"done", "error"},
                "updated": now,
            }
            if len(self._items) > self._max_items:
                for key in [k for k, v in self._items.items() if now - float(v["updated"]) > self._ttl]:
                    self._items.pop(key, None)

    def get(self, job_id: str) -> dict[str, object]:
        with self._lock:
            item = self._items.get(job_id)
        if item is None:
            return {"stage": "waiting", "label": STAGE_LABELS["waiting"], "percent": 0.0, "done": False}
        return {k: v for k, v in item.items() if k != "updated"}


def _load_model(app: FastAPI) -> None:
    """Модель создаётся один раз при старте и переиспользуется всеми запросами.

    Загрузка идёт в фоновом потоке: порт открывается сразу (хостингу вроде Render
    это важно), а до готовности модели /transcribe отвечает 503.
    """
    try:
        app.state.transcriber = WhisperTranscriber(
            config.model,
            config.language,
            cpu_threads=config.cpu_threads,
            beam_size=config.beam_size,
            initial_prompt=config.initial_prompt,
        )
        logger.info("Модель %s загружена", config.model)
    except Exception as exc:  # noqa: BLE001
        app.state.model_error = str(exc)
        logger.exception("Не удалось загрузить модель %s", config.model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.decoder = AudioDecoder(
        config.max_audio_seconds,
        config.allowed_extensions,
        int(config.max_upload_mb * 1024 * 1024),
        preprocess=config.preprocess_audio,
    )
    app.state.progress = ProgressTracker()
    app.state.transcriber = None
    app.state.model_error = None
    if os.getenv("SII_LR03_SKIP_MODEL") != "1":
        threading.Thread(target=_load_model, args=(app,), daemon=True).start()
    yield


app = FastAPI(
    title="SII-LR03 — Whisper и ключевые слова",
    version=config.model_version,
    description="Аудиосервис: декодирование → Whisper → текст → поиск ключевых слов.",
    lifespan=lifespan,
)

BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/samples", StaticFiles(directory=BASE_DIR / "samples"), name="samples")

@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
def ready() -> dict[str, object]:
    """Готова ли модель (на холодном старте free-хостинга это не сразу)."""
    return {
        "model_loaded": app.state.transcriber is not None,
        "error": app.state.model_error,
    }


@app.get("/progress/{job_id}", include_in_schema=False)
def progress(job_id: str) -> dict[str, object]:
    """Прогресс текущей обработки: этап и процент (для индикатора в интерфейсе)."""
    return app.state.progress.get(job_id)


@app.get("/scenario", include_in_schema=False)
def scenario() -> dict[str, object]:
    """Параметры сценария из YAML — для веб-интерфейса."""
    return {
        "scenario_id": config.scenario_id,
        "scenario_name": config.scenario_name,
        "keywords": config.keywords,
        "max_audio_seconds": config.max_audio_seconds,
        "language": config.language,
        "model": config.model_display_name,
    }


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    x_job_id: str | None = Header(default=None),
) -> TranscriptionResponse | JSONResponse:
    started = time.perf_counter()
    source: Path | None = None
    wav_path: Path | None = None
    tracker: ProgressTracker = app.state.progress
    job_id = x_job_id if x_job_id and _JOB_ID_RE.match(x_job_id) else None
    try:
        decoder = app.state.decoder
        tracker.set(job_id, "decode", 2)
        source = await decoder.save_upload(file)
        tracker.set(job_id, "decode", 5)
        # ffprobe/ffmpeg/Whisper блокирующие — уводим их из event loop,
        # иначе /health и другие запросы «замирают» на время распознавания.
        await run_in_threadpool(decoder.duration_seconds, source)
        wav_path = await run_in_threadpool(decoder.decode_to_wav, source)
        tracker.set(job_id, "transcribe", 12)
        transcriber = app.state.transcriber
        if transcriber is None:
            tracker.set(job_id, "error", 0)
            if app.state.model_error:
                return _error(503, "Модель Whisper не удалось загрузить: " + app.state.model_error)
            return _error(503, "Модель Whisper ещё загружается, повторите через 10–30 секунд.")

        def on_progress(fraction: float) -> None:
            # распознавание занимает отрезок 12 % … 95 % общего прогресса
            tracker.set(job_id, "transcribe", 12 + 83 * fraction)

        kwargs = {}
        if "on_progress" in inspect.signature(transcriber.transcribe).parameters:
            kwargs["on_progress"] = on_progress
        text, segments = await run_in_threadpool(lambda: transcriber.transcribe(str(wav_path), **kwargs))
        if not text:
            raise EmptyAudioError("Whisper не обнаружил речь в аудиофайле.")

        tracker.set(job_id, "keywords", 97)
        # Тишину, добавленную по краям при подготовке звука, вычитаем из таймкодов.
        pad = decoder.pad_seconds
        segments = [
            Segment(max(0.0, seg.start - pad), max(0.0, seg.end - pad), seg.text) for seg in segments
        ]
        matches = find_keywords(text, config.keywords)
        latency_ms = int((time.perf_counter() - started) * 1000)
        tracker.set(job_id, "done", 100)
        return TranscriptionResponse(
            scenario_id=config.scenario_id,
            scenario_name=config.scenario_name,
            text=text,
            language=config.language,
            segments=[SegmentResponse(**segment.__dict__) for segment in segments],
            keywords_found=[KeywordResponse(keyword=m.keyword, count=m.count) for m in matches],
            model=config.model_display_name,
            model_version=config.model_version,
            latency_ms=latency_ms,
        )
    except EmptyAudioError as exc:
        tracker.set(job_id, "error", 0)
        return _error(400, str(exc))
    except UnsupportedAudioError as exc:
        tracker.set(job_id, "error", 0)
        return _error(415, str(exc))
    except (AudioTooLongError, FileTooLargeError) as exc:
        tracker.set(job_id, "error", 0)
        return _error(413, str(exc))
    except Exception as exc:  # noqa: BLE001 — любой сбой модели/декодера отдаём как JSON
        logger.exception("Ошибка при обработке аудио")
        tracker.set(job_id, "error", 0)
        reason = f"{type(exc).__name__}: {exc}"[:300]
        return _error(500, f"Внутренняя ошибка при распознавании аудио. {reason}")
    finally:
        if source is not None:
            source.unlink(missing_ok=True)
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)
        await file.close()
