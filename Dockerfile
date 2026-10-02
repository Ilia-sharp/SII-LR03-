FROM python:3.12-slim

# ffmpeg/ffprobe нужны для декодирования аудио
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.cache/huggingface \
    WHISPER_MODEL=tiny \
    WHISPER_CPU_THREADS=1 \
    WHISPER_BEAM_SIZE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Модель скачиваем при сборке образа: на free-плане Render диск не сохраняется,
# и иначе она скачивалась бы заново при каждом пробуждении сервиса.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"

COPY . .

# Render передаёт порт в $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
