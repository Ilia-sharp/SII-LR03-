from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KeywordMatch:
    keyword: str
    count: int


_word_re = re.compile(r"[\wёЁ-]+", re.UNICODE)
# Окончания, которые отбрасываем при построении основы: мойка → мойк, запись → запис.
_ENDING_RE = re.compile(r"[аяуюыиеоэьй]+$")
_MIN_STEM_LEN = 4


def normalize_text(text: str) -> str:
    return " ".join(_word_re.findall(text.lower().replace("ё", "е"))).strip()


def stem(keyword: str) -> str | None:
    """Основа слова для поиска словоформ (None — нужно только точное совпадение).

    Whisper пишет слова так, как их сказали: «на мойку», «мойки», «записаться»,
    «записи». Точное сравнение с «мойка»/«запись» такие формы пропускало бы,
    поэтому ищем по основе: мойка → мойк, запись → запис, кузов → кузов
    (кузова, кузову…). Для коротких слов (< 4 букв в основе) остаётся точное
    совпадение, чтобы не ловить посторонние слова.
    """
    base = _ENDING_RE.sub("", normalize_text(keyword))
    return base if len(base) >= _MIN_STEM_LEN else None


def find_keywords(text: str, keywords: list[str]) -> list[KeywordMatch]:
    tokens = normalize_text(text).split()
    matches: list[KeywordMatch] = []

    for keyword in keywords:
        key = normalize_text(keyword)
        if not key:
            continue
        base = stem(keyword)
        if base is None:
            count = sum(1 for token in tokens if token == key)
        else:
            count = sum(1 for token in tokens if token.startswith(base))
        if count:
            matches.append(KeywordMatch(keyword=keyword, count=count))

    return matches
