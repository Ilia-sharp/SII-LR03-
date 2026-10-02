"""Ловит поломку зависимостей (например, несовместимый av) без загрузки модели."""
import glob
import os

from faster_whisper.audio import decode_audio
from faster_whisper.vad import VadOptions, get_speech_timestamps

SAMPLE = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "samples", "*.wav")))[0]


def test_faster_whisper_can_decode_audio() -> None:
    audio = decode_audio(SAMPLE, sampling_rate=16000)
    assert len(audio) > 16000  # больше секунды звука


def test_vad_runs_on_sample() -> None:
    audio = decode_audio(SAMPLE, sampling_rate=16000)
    assert get_speech_timestamps(audio, VadOptions())


def test_whisper_call_matches_faster_whisper_signature() -> None:
    """Параметры, которые мы передаём в Whisper, должны существовать в установленной версии."""
    import inspect
    from types import SimpleNamespace

    from faster_whisper import WhisperModel
    from faster_whisper.vad import VadOptions

    from app.asr import WhisperTranscriber

    captured: dict = {}

    class FakeModel:
        def transcribe(self, wav_path, **kwargs):
            captured.update(kwargs)
            segment = SimpleNamespace(start=0.0, end=2.0, text=" нужна мойка ")
            return iter([segment]), SimpleNamespace(duration=2.0)

    transcriber = WhisperTranscriber.__new__(WhisperTranscriber)
    transcriber.model, transcriber.language = FakeModel(), "ru"
    transcriber.beam_size, transcriber.initial_prompt = 1, "Клиент автомойки."
    progress: list[float] = []
    text, segments = transcriber.transcribe("x.wav", on_progress=progress.append)

    inspect.signature(WhisperModel.transcribe).bind(None, "x.wav", **captured)  # бросит TypeError при опечатке
    assert set(captured["vad_parameters"]) <= set(VadOptions.__dataclass_fields__)
    assert text == "нужна мойка" and len(segments) == 1
    assert progress[-1] == 1.0
