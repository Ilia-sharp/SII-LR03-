from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.asr import WhisperTranscriber
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
    )
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
async def transcribe(file: UploadFile = File(...)) -> TranscriptionResponse | JSONResponse:
    started = time.perf_counter()
    source: Path | None = None
    wav_path: Path | None = None
    try:
        decoder = app.state.decoder
        source = await decoder.save_upload(file)
        # ffprobe/ffmpeg/Whisper блокирующие — уводим их из event loop,
        # иначе /health и другие запросы «замирают» на время распознавания.
        await run_in_threadpool(decoder.duration_seconds, source)
        wav_path = await run_in_threadpool(decoder.decode_to_wav, source)
        transcriber = app.state.transcriber
        if transcriber is None:
            if app.state.model_error:
                return _error(503, "Модель Whisper не удалось загрузить: " + app.state.model_error)
            return _error(503, "Модель Whisper ещё загружается, повторите через 10–30 секунд.")
        text, segments = await run_in_threadpool(transcriber.transcribe, str(wav_path))
        if not text:
            raise EmptyAudioError("Whisper не обнаружил речь в аудиофайле.")

        matches = find_keywords(text, config.keywords)
        latency_ms = int((time.perf_counter() - started) * 1000)
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
        return _error(400, str(exc))
    except UnsupportedAudioError as exc:
        return _error(415, str(exc))
    except (AudioTooLongError, FileTooLargeError) as exc:
        return _error(413, str(exc))
    except Exception:  # noqa: BLE001 — любой сбой модели/декодера отдаём как JSON
        logger.exception("Ошибка при обработке аудио")
        return _error(500, "Внутренняя ошибка при распознавании аудио.")
    finally:
        if source is not None:
            source.unlink(missing_ok=True)
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)
        await file.close()
