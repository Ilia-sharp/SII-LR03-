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
