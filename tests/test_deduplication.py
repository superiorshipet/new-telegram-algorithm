from sqlalchemy import UniqueConstraint

from app.database.models import CollectedMessage
from app.filtering.rules import build_content_hash, message_identity


def test_same_message_seen_by_two_accounts_has_same_identity_and_hash() -> None:
    first_identity = message_identity(-100123456, 42)
    second_identity = message_identity(-100123456, 42)
    first_hash = build_content_hash(-100123456, 42, "مطلوب مطور")
    second_hash = build_content_hash(-100123456, 42, "مطلوب مطور")

    assert first_identity == second_identity
    assert first_hash == second_hash


def test_different_group_or_message_changes_deduplication_key() -> None:
    assert message_identity(-1001, 10) != message_identity(-1002, 10)
    assert message_identity(-1001, 10) != message_identity(-1001, 11)


def test_database_enforces_atomic_group_message_uniqueness() -> None:
    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in CollectedMessage.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert constraints["uq_collected_messages_group_message"] == (
        "telegram_group_id",
        "telegram_message_id",
    )
