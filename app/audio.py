from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from fastapi import UploadFile


class AudioError(Exception):
    """Base class for audio validation/decoding errors."""


class EmptyAudioError(AudioError):
    pass


class UnsupportedAudioError(AudioError):
    pass


class AudioTooLongError(AudioError):
    pass


class FileTooLargeError(AudioError):
    pass


class AudioDecoder:
    def __init__(
        self,
        max_seconds: float,
        allowed_extensions: list[str],
        max_upload_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        self.max_seconds = max_seconds
        self.max_upload_bytes = max_upload_bytes
        self.allowed_extensions = {ext.lower() for ext in allowed_extensions}

    async def save_upload(self, upload: UploadFile) -> Path:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in self.allowed_extensions:
            raise UnsupportedAudioError(
                "Неподдерживаемый формат. Допустимы: "
                + ", ".join(sorted(self.allowed_extensions))
            )

        # Читаем кусками прямо во временный файл: на 512 МБ RAM нельзя держать
        # весь файл в памяти, а слишком большой файл надо отсечь сразу.
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        path = Path(tmp.name)
        size = 0
        try:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > self.max_upload_bytes:
                    raise FileTooLargeError(
                        f"Файл слишком большой (лимит {self.max_upload_bytes // (1024 * 1024)} МБ)."
                    )
                tmp.write(chunk)
        except Exception:
            tmp.close()
            path.unlink(missing_ok=True)
            raise
        tmp.close()
        if size == 0:
            path.unlink(missing_ok=True)
            raise EmptyAudioError("Аудиофайл пустой.")
        return path

    def duration_seconds(self, path: Path) -> float:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise UnsupportedAudioError("Не удалось декодировать аудиофайл.")
        try:
            duration = float(result.stdout.strip())
        except ValueError as exc:
            raise UnsupportedAudioError("Не удалось определить длительность аудио.") from exc
        if duration <= 0:
            raise EmptyAudioError("Аудиофайл не содержит звука.")
        if duration > self.max_seconds:
            raise AudioTooLongError(
                f"Длина аудио {duration:.1f} с превышает лимит {self.max_seconds:.0f} с."
            )
        return duration

    def decode_to_wav(self, source: Path) -> Path:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        target = Path(tmp.name)
        tmp.close()
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            target.unlink(missing_ok=True)
            raise UnsupportedAudioError("Файл не удалось привести к WAV/16 kHz для Whisper.")
        return target
