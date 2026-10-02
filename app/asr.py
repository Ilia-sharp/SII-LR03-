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
        segments_iter, info = self.model.transcribe(
            wav_path,
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.initial_prompt,
            # Если на температуре 0 результат «подозрительный» (повторы, низкая
            # уверенность), модель сама пробует ещё раз с небольшой случайностью.
            temperature=[0.0, 0.2, 0.4],
            # Короткие независимые реплики: контекст предыдущего сегмента не нужен
            # и только провоцирует повторы.
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 400},
        )
        total = float(getattr(info, "duration", 0.0) or 0.0)
        segments: list[Segment] = []
        text_parts: list[str] = []
        # Whisper отдаёт сегменты по мере готовности — по ним считаем реальный прогресс.
        for item in segments_iter:
            segment = Segment(
                start=float(item.start),
                end=float(item.end),
                text=item.text.strip(),
            )
            segments.append(segment)
            if segment.text:
                text_parts.append(segment.text)
            if on_progress and total > 0:
                on_progress(min(1.0, segment.end / total))
        if on_progress:
            on_progress(1.0)
        return " ".join(text_parts).strip(), segments
