from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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
