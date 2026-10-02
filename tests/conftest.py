import os

# Unit-тесты не должны скачивать и загружать модель Whisper —
# выставляем флаг до импорта app.main, независимо от порядка тестов.
os.environ.setdefault("SII_LR03_SKIP_MODEL", "1")
