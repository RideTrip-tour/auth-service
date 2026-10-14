from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.user_manager import UserManager


# --- UserManager helpers ---
@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (3600, "1 час"),
        (7200, "2 часа"),
        (10800, "3 часа"),
        (18000, "5 часов"),
        (39600, "11 часов"),
        (60, "1 минуту"),
        (120, "2 минуты"),
        (300, "5 минут"),
        (660, "11 минут"),
        (1, "1 секунд"),
    ],
)
def test_format_lifetime(seconds, expected):
    assert UserManager._format_lifetime(seconds) == expected


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("user@example.com", "u***@example.com"),
        ("a@example.com", "a***@example.com"),
        ("user", "user"),
        ("@example.com", "****@example.com"),
    ],
)
def test_mask_email(email, expected):
    assert UserManager._mask_email(email) == expected


@pytest.mark.asyncio
async def test_change_password_success(user_manager):
    user = SimpleNamespace(
        id=1,
        hashed_password="old-hash",
    )

    user_manager.password_helper.verify_and_update = MagicMock(
        return_value=(True, None)
    )
    user_manager.password_helper.hash = MagicMock(return_value="new-hash")
    user_manager.validate_password = AsyncMock()
    user_manager.on_after_update = AsyncMock()

    session = AsyncMock()
    session.execute.return_value.rowcount = 1

    user_manager.user_db.session = session

    result = await user_manager.change_password(
        user=user,
        current_password="old-password",
        new_password="new-password",
    )
    assert result is user

    user_manager.validate_password.assert_awaited_once_with(
        "new-password",
        user,
    )
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)

    user_manager.on_after_update.assert_awaited_once_with(
        user,
        {"hashed_password": "new-hash"},
        None,
    )


@pytest.mark.asyncio
async def test_delete_account_success(user_manager, user):
    user_manager._soft_delete_account = AsyncMock()
    user_manager._log_account_deletion = AsyncMock()
    user_manager._send_account_deletion_email = AsyncMock()

    with patch("app.services.user_manager.get_strategy") as get_strategy_mock:
        strategy = get_strategy_mock.return_value
        strategy.destroy_tokens_by_user = AsyncMock()

        await user_manager.delete_account(user)

    user_manager._soft_delete_account.assert_awaited_once_with(user)
    strategy.destroy_tokens_by_user.assert_awaited_once_with(user)
    user_manager._log_account_deletion.assert_awaited_once_with(user, None)
    user_manager._send_account_deletion_email.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_delete_account_already_deleted(user_manager, user):
    user.deleted_at = datetime.now(UTC)

    with pytest.raises(HTTPException) as exc_info:
        await user_manager.delete_account(user)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Account already deleted"


@pytest.mark.asyncio
async def test_soft_delete_account_success(user_manager, user):
    session = AsyncMock()
    user_manager.user_db.session = session

    await user_manager._soft_delete_account(user)

    user.soft_delete.assert_called_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_account_deletion_email(user_manager, user):
    user.deleted_at = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)

    with patch(
        "app.services.user_manager.send_email", new_callable=AsyncMock
    ) as send_email_mock:
        await user_manager._send_account_deletion_email(user)

    send_email_mock.assert_awaited_once()

    args, kwargs = send_email_mock.call_args

    assert args[0] == user.email
    assert args[1] == "Удаление аккаунта — 3шагадо"
    assert "28.10.2026 10:00 UTC" in args[2]
    assert kwargs["html"] is False
