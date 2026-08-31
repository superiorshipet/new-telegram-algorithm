import uuid
from datetime import UTC, datetime

from app.collector.status import format_account_status
from app.database.models import SourceAccount


def source_account(name: str, status: str, *, active: bool = True) -> SourceAccount:
    return SourceAccount(
        id=uuid.uuid4(),
        name=name,
        session_string_encrypted="encrypted-session",
        api_id_encrypted="encrypted-api-id",
        api_hash_encrypted="encrypted-api-hash",
        is_active=active,
        status=status,
        last_connected_at=datetime(2026, 8, 31, 20, 0, tzinfo=UTC),
    )


def test_status_summary_counts_only_active_connected_accounts() -> None:
    rendered = format_account_status(
        [
            source_account("الحساب الاول", "connected"),
            source_account("الحساب الثاني", "unauthorized"),
            source_account("الحساب الثالث", "connected", active=False),
        ]
    )

    assert "total=3 active=2 connected=1" in rendered
    assert "الحساب الاول: status=connected" in rendered
    assert "الحساب الثاني: status=unauthorized" in rendered
    assert "الحساب الثالث: status=connected active=false" in rendered
