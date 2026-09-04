import uuid

from sqlalchemy.dialects import postgresql

from app.database.repositories.messages import _notification_outbox_insert


def test_outbox_insert_generates_a_distinct_database_uuid_for_each_recipient() -> None:
    statement = _notification_outbox_insert(uuid.uuid4())

    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "gen_random_uuid()" in compiled_sql
    assert "(id, collected_message_id, bot_user_id, available_at)" in compiled_sql
    assert "%(id)s::UUID" not in compiled_sql
    assert "now()" in compiled_sql
    assert "interval '1 second'" not in compiled_sql
