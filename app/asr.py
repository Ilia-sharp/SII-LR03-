from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


class WhisperTranscriber:
    """Whisper model is loaded once and reused for all HTTP requests."""

    def __init__(
        self,
        model_name: str,
        language: str = "ru",
        cpu_threads: int = 0,
        beam_size: int = 5,
        initial_prompt: str = "",
    ) -> None:
        self.initial_prompt = initial_prompt.strip() or None
        self.model_name = model_name
        self.language = language
        self.beam_size = beam_size
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
            num_workers=1,
        )

    def transcribe(
        self,
        wav_path: str,
        on_progress: Callable[[float], None] | None = None,
    ) -> tuple[str, list[Segment]]:
        # Точность важнее скорости: сначала основной проход (со словарём и VAD),
        # а если речь не найдена — второй, «страховочный», без подсказки и VAD.
        text, segments = self._run(wav_path, on_progress, strict=True)
        if not text:
            text, segments = self._run(wav_path, on_progress, strict=False)
        if on_progress:
            on_progress(1.0)
        return text, segments

    def _run(
        self,
        wav_path: str,
        on_progress: Callable[[float], None] | None,
        *,
        strict: bool,
    ) -> tuple[str, list[Segment]]:
        options: dict = {
            "language": self.language,
            "beam_size": self.beam_size,
            # Перебираем больше вариантов и ждём дольше, пока луч «созреет».
            "patience": 1.5,
            "best_of": 5,
            # Если на температуре 0 результат «подозрительный» (повторы, низкая
            # уверенность), модель сама пробует ещё раз с небольшой случайностью.
            "temperature": [0.0, 0.2, 0.4, 0.6],
            # Короткие независимые реплики: контекст предыдущего сегмента не нужен
            # и только провоцирует повторы.
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "log_prob_threshold": -1.0,
            "compression_ratio_threshold": 2.4,
        }
        if strict:
            options["initial_prompt"] = self.initial_prompt
            options["vad_filter"] = True
            options["vad_parameters"] = {"min_silence_duration_ms": 400, "speech_pad_ms": 400}
        else:
            options["vad_filter"] = False

        segments_iter, info = self.model.transcribe(wav_path, **options)
        total = float(getattr(info, "duration", 0.0) or 0.0)
        segments: list[Segment] = []
        text_parts: list[str] = []
        # Whisper отдаёт сегменты по мере готовности — по ним считаем реальный прогресс.
        for item in segments_iter:
            segment = Segment(start=float(item.start), end=float(item.end), text=item.text.strip())
            segments.append(segment)
            if segment.text:
                text_parts.append(segment.text)
            if on_progress and total > 0:
                on_progress(min(0.99, segment.end / total))
        return " ".join(text_parts).strip(), segments
