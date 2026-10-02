from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    ) -> None:
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

    def transcribe(self, wav_path: str) -> tuple[str, list[Segment]]:
        segments_iter, _info = self.model.transcribe(
            wav_path,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
        )
        segments: list[Segment] = []
        text_parts: list[str] = []
        for item in segments_iter:
            segment = Segment(
                start=float(item.start),
                end=float(item.end),
                text=item.text.strip(),
            )
            segments.append(segment)
            if segment.text:
                text_parts.append(segment.text)
        return " ".join(text_parts).strip(), segments
