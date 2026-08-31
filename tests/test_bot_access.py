import pytest

from app.database.repositories.bot_access import parse_access_subject


def test_access_subject_accepts_telegram_user_id() -> None:
    subject = parse_access_subject(" 123456789 ")

    assert subject.subject_type == "telegram_id"
    assert subject.subject_value == "123456789"
    assert subject.display == "123456789"


def test_access_subject_normalizes_username() -> None:
    subject = parse_access_subject(" @Shipet_004 ")

    assert subject.subject_type == "username"
    assert subject.subject_value == "shipet_004"
    assert subject.display == "@shipet_004"


@pytest.mark.parametrize("value", ["", "+201234567890", "username", "@bad-name"])
def test_access_subject_rejects_phone_numbers_and_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_access_subject(value)
