from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "keywords.yaml"


class ScenarioConfig(BaseModel):
    scenario_id: str
    scenario_name: str
    keywords: list[str] = Field(min_length=1)
    language: str = "ru"
    model: str = "base"
    model_display_name: str = "whisper-base"
    model_version: str = "v1.0"
    max_audio_seconds: float = 60.0
    max_upload_mb: float = 25.0
    cpu_threads: int = 0  # 0 = решает библиотека; на Render free ставим 1
    beam_size: int = 5
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"]
    )


def load_config(path: Path = CONFIG_PATH) -> ScenarioConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = ScenarioConfig.model_validate(raw)

    # Переопределения для слабых хостингов (Render free: 0.1 CPU / 512 МБ RAM).
    # Значения из YAML остаются значениями по умолчанию для локального запуска.
    if os.getenv("WHISPER_MODEL"):
        config.model = os.environ["WHISPER_MODEL"].strip()
        config.model_display_name = f"whisper-{config.model}"
    if os.getenv("WHISPER_CPU_THREADS"):
        config.cpu_threads = int(os.environ["WHISPER_CPU_THREADS"])
    if os.getenv("WHISPER_BEAM_SIZE"):
        config.beam_size = int(os.environ["WHISPER_BEAM_SIZE"])
    if os.getenv("MAX_UPLOAD_MB"):
        config.max_upload_mb = float(os.environ["MAX_UPLOAD_MB"])
    return config
