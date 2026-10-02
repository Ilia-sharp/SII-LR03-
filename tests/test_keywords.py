from app.keywords import find_keywords


def test_keywords_case_and_punctuation() -> None:
    text = "Нужна МОЙКА, кузов и салон. Нужна запись!"
    result = find_keywords(text, ["мойка", "кузов", "салон", "запись"])
    assert [(item.keyword, item.count) for item in result] == [
        ("мойка", 1),
        ("кузов", 1),
        ("салон", 1),
        ("запись", 1),
    ]


def test_repeated_keyword() -> None:
    result = find_keywords("мойка мойка кузов", ["мойка", "кузов", "салон", "запись"])
    assert result[0].count == 2


KEYWORDS = ["мойка", "кузов", "салон", "запись"]


def test_word_forms() -> None:
    text = "Хочу записаться на мойку кузова, потом химчистка салона. Подтвердите запись."
    result = {item.keyword: item.count for item in find_keywords(text, KEYWORDS)}
    assert result == {"мойка": 1, "кузов": 1, "салон": 1, "запись": 2}  # записаться + запись


def test_other_cases_of_wash_and_record() -> None:
    result = {item.keyword: item.count for item in find_keywords("мойки, мойкой, записи, записью", KEYWORDS)}
    assert result == {"мойка": 2, "запись": 2}


def test_no_false_positives() -> None:
    assert find_keywords("Добрый день, погода хорошая, где тут парковка?", KEYWORDS) == []


def test_yo_and_empty_text() -> None:
    assert find_keywords("", KEYWORDS) == []
    assert [m.keyword for m in find_keywords("Ёлка и салон", ["салон"])] == ["салон"]


def test_short_keyword_is_exact_only() -> None:
    assert [m.count for m in find_keywords("кот коты котел", ["кот"])] == [1]
