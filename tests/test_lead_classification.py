import pytest

from app.bot.services import default_filter_values
from app.filtering import build_text_fingerprint, classify_lead, normalize_arabic


def normalized_default_keywords() -> list[str]:
    return [normalized for _, normalized in default_filter_values()]


def test_request_phrase_and_keyword_create_a_lead() -> None:
    text = normalize_arabic("مين يسوي ارقام سعودي واتس")
    result = classify_lead(text, normalized_default_keywords())

    assert result.is_lead is True
    assert "يسوي" in result.matched_keywords
    assert "مين يسوي" in result.matched_intents
    assert result.score >= 4


def test_keyword_without_request_context_does_not_alert() -> None:
    text = normalize_arabic("هذا مشروع جميل تم عرضه في الجامعة")
    result = classify_lead(text, normalized_default_keywords())

    assert "مشروع" in result.matched_keywords
    assert result.is_lead is False


def test_request_word_alone_does_not_alert() -> None:
    result = classify_lead(normalize_arabic("احتاج"), normalized_default_keywords())
    assert result.matched_keywords == ("احتاج",)
    assert result.is_lead is False


def test_custom_keyword_still_requires_request_context() -> None:
    text = normalize_arabic("أحتاج خبير شبكات يساعدني")
    result = classify_lead(text, [normalize_arabic("خبير شبكات")])

    assert result.is_lead is True
    assert result.matched_keywords == ("خبير شبكات",)


@pytest.mark.parametrize(
    "text",
    [
        (
            "هو أهم من اختيار الشبكة المواصفات حجم الرام، "
            "أنا عندي لابتوب ديل gaming قوي بصراحة"
        ),
        "انا باذن الله، لكن عندي كلاس الساعة ١ بالتحضيري اخاف اتأخر",
        "تفضل هذا المشروع الذي تحدثنا عنه",
        "الدكتور يشرح برنامج اليوم",
    ],
)
def test_informational_keyword_context_does_not_alert(text: str) -> None:
    result = classify_lead(normalize_arabic(text), normalized_default_keywords())

    assert result.matched_keywords
    assert result.is_lead is False


@pytest.mark.parametrize(
    "text",
    [
        "احتاج شخص يصمم لي عرض للمشروع",
        "حد فاهم اكسل يساعدني في واجب؟",
        "يشرح واجب رياضيات؟",
    ],
)
def test_keyword_with_request_intent_and_context_alerts(text: str) -> None:
    result = classify_lead(normalize_arabic(text), normalized_default_keywords())

    assert result.is_lead is True
    assert result.matched_keywords
    assert result.matched_intents


def test_text_fingerprint_is_independent_from_group_identity() -> None:
    normalized = normalize_arabic("محتاج مشروع تخرج")
    with_punctuation = normalize_arabic("محتاج، مشروع تخرج!!!")
    assert build_text_fingerprint(normalized) == build_text_fingerprint(with_punctuation)
    assert build_text_fingerprint(normalized) != build_text_fingerprint("نص مختلف")
