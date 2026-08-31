from app.filtering.normalizer import normalize_arabic


def test_normalizes_arabic_letter_variants_diacritics_and_whitespace() -> None:
    assert normalize_arabic("  إِعْلَانٌ   عَن  فُرْصَةٍ  ") == "اعلان عن فرصه"


def test_removes_tatweel_and_normalizes_alef_maqsura() -> None:
    assert normalize_arabic("علــى") == "علي"


def test_casefolds_latin_without_removing_arabic_punctuation() -> None:
    assert normalize_arabic("  Python،  مُطَوِّر  ") == "python، مطور"
