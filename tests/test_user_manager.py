from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi_users import exceptions

from app.exceptions.users import UserUpdateFailed
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

    user_manager.user_db.compare_and_update_committed = AsyncMock(return_value=user)

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

    user_manager.user_db.compare_and_update_committed.assert_awaited_once_with(
        user,
        {"hashed_password": "new-hash"},
        ("hashed_password",),
    )

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

    await user_manager.delete_account(user)

    user_manager._soft_delete_account.assert_awaited_once_with(user)
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

    with (
        patch(
            "app.services.user_manager.SQLAlchemyRefreshTokenDatabase"
        ) as token_db_cls,
        patch.object(user, "soft_delete", wraps=user.soft_delete) as soft_delete,
    ):
        token_db = token_db_cls.return_value
        token_db.delete_by_user_id = AsyncMock()

        await user_manager._soft_delete_account(user)

    soft_delete.assert_called_once()
    token_db.delete_by_user_id.assert_awaited_once_with(user.id)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_account_deletion_email(user_manager, user):
    user.deleted_at = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)

    user_manager._generate_password_recovery_token = MagicMock(
        return_value="test-token"
    )

    with patch(
        "app.services.user_manager.send_email",
        new_callable=AsyncMock,
    ) as send_email_mock:
        await user_manager._send_account_deletion_email(user)

    user_manager._generate_password_recovery_token.assert_called_once_with(
        user,
        lifetime_seconds=14 * 24 * 60 * 60,
    )

    send_email_mock.assert_awaited_once()

    args, kwargs = send_email_mock.call_args

    assert args[0] == user.email
    assert args[1] == "Удаление аккаунта — 3шагадо"
    assert "28.10.2026 10:00 UTC" in args[2]
    assert "test-token" in args[2]
    assert kwargs["html"] is True


@pytest.mark.asyncio
async def test_update_user_success(user_manager, user):
    session = AsyncMock()
    session.execute.return_value = MagicMock(rowcount=1)
    user_manager.user_db.session = session

    result = await user_manager._update_user(
        user,
        {"is_active": True},
        ("is_active",),
    )

    assert result is user
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_password_success(user_manager, user):
    updated_user = MagicMock()
    data = {
        "sub": str(user.id),
        "password_fgpt": "password-fingerprint",
    }

    with (
        patch(
            "app.services.user_manager.decode_jwt",
            return_value=data,
        ),
        patch.object(user_manager, "parse_id", return_value=user.id),
        patch.object(user_manager, "get", new_callable=AsyncMock, return_value=user),
        patch.object(
            user_manager.password_helper,
            "verify_and_update",
            return_value=(True, None),
        ),
        patch.object(
            user_manager,
            "_update",
            new_callable=AsyncMock,
            return_value=updated_user,
        ),
        patch.object(
            user_manager, "on_after_reset_password", new_callable=AsyncMock
        ) as callback,
    ):
        user.deleted_at = None
        user.is_active = True

        result = await user_manager.reset_password(
            token="valid-token",
            password="NewPassword123!",
        )

    assert result is updated_user
    callback.assert_awaited_once_with(updated_user, None)


@pytest.mark.asyncio
async def test_reset_password_restore_account(user_manager, user):
    data = {
        "sub": str(user.id),
        "password_fgpt": "password-fingerprint",
    }

    with (
        patch(
            "app.services.user_manager.decode_jwt",
            return_value=data,
        ),
        patch.object(user_manager, "parse_id", return_value=user.id),
        patch.object(user_manager, "get", new_callable=AsyncMock, return_value=user),
        patch.object(
            user_manager.password_helper,
            "verify_and_update",
            return_value=(True, None),
        ),
        patch.object(
            user_manager,
            "_restore_account",
            new_callable=AsyncMock,
            return_value=user,
        ) as restore_mock,
    ):
        user.deleted_at = MagicMock()

        result = await user_manager.reset_password(
            token="valid-token",
            password="NewPassword123!",
        )

    assert result is user
    restore_mock.assert_awaited_once_with(user, "NewPassword123!", None)


@pytest.mark.asyncio
async def test_restore_account_success(user_manager, user, transaction):
    user.deleted_at = datetime.now(UTC) - timedelta(days=1)
    user.hashed_password = "old-hash"
    user.is_active = False

    with (
        patch(
            "app.services.user_manager.settings.account_restore_period_days",
            14,
        ),
        patch.object(
            user_manager,
            "validate_password",
            new_callable=AsyncMock,
        ) as validate_password_mock,
        patch.object(
            user_manager.password_helper,
            "hash",
            return_value="new-hash",
        ) as hash_mock,
        patch.object(
            user_manager.user_db,
            "compare_and_update",
            new_callable=AsyncMock,
            return_value=user,
            create=True,
        ) as update_mock,
        patch.object(
            user_manager.gateway_client,
            "restore_profile",
            new_callable=AsyncMock,
        ) as restore_profile_mock,
        patch.object(
            user_manager,
            "on_after_account_restore",
            new_callable=AsyncMock,
        ) as callback_mock,
    ):
        result = await user_manager._restore_account(
            user,
            "NewPassword123!",
        )

    assert result is user

    validate_password_mock.assert_awaited_once_with(
        "NewPassword123!",
        user,
    )
    hash_mock.assert_called_once_with("NewPassword123!")

    update_mock.assert_awaited_once_with(
        user,
        {
            "hashed_password": "new-hash",
            "is_active": True,
            "deleted_at": None,
        },
        ("hashed_password", "deleted_at", "is_active"),
    )

    restore_profile_mock.assert_awaited_once_with(user)
    callback_mock.assert_awaited_once_with(user, None)

    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
async def test_restore_account_expired(user_manager, user):
    user.deleted_at = datetime.now(UTC) - timedelta(days=15)

    with (
        patch(
            "app.services.user_manager.settings.account_restore_period_days",
            14,
        ),
        patch.object(
            user_manager.gateway_client,
            "delete_profile_permanently",
            new_callable=AsyncMock,
        ) as delete_profile_mock,
        patch.object(
            user_manager.user_db,
            "delete",
            new_callable=AsyncMock,
        ) as delete_user_mock,
        patch.object(
            user_manager,
            "validate_password",
            new_callable=AsyncMock,
        ) as validate_password_mock,
        pytest.raises(exceptions.InvalidResetPasswordToken),
    ):
        await user_manager._restore_account(
            user,
            "NewPassword123!",
        )

    delete_profile_mock.assert_awaited_once_with(user)
    delete_user_mock.assert_awaited_once_with(user)
    validate_password_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_restore_account_profile_error_rollbacks_auth(
    user_manager,
    user,
    transaction,
):
    updated_user = MagicMock()

    user.hashed_password = "old-hash"
    user.is_active = False
    user.deleted_at = datetime.now(UTC) - timedelta(days=1)

    with (
        patch.object(
            user_manager,
            "_is_restore_period_expired",
            return_value=False,
        ),
        patch.object(
            user_manager,
            "validate_password",
            new_callable=AsyncMock,
        ),
        patch.object(
            user_manager.password_helper,
            "hash",
            return_value="new-hash",
        ),
        patch.object(
            user_manager.user_db,
            "compare_and_update",
            new_callable=AsyncMock,
            return_value=updated_user,
            create=True,
        ) as update_mock,
        patch.object(
            user_manager.gateway_client,
            "restore_profile",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Profile service error"),
        ) as restore_profile_mock,
        patch.object(
            user_manager,
            "on_after_account_restore",
            new_callable=AsyncMock,
        ) as callback_mock,
        pytest.raises(UserUpdateFailed) as exc_info,
    ):
        await user_manager._restore_account(
            user,
            "NewPassword123!",
        )

    assert isinstance(exc_info.value.__cause__, RuntimeError)

    update_mock.assert_awaited_once_with(
        user,
        {
            "hashed_password": "new-hash",
            "is_active": True,
            "deleted_at": None,
        },
        ("hashed_password", "deleted_at", "is_active"),
    )

    restore_profile_mock.assert_awaited_once_with(updated_user)
    callback_mock.assert_not_awaited()

    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()

    assert transaction.__aexit__.await_args.args[0] is RuntimeError
    assert isinstance(
        transaction.__aexit__.await_args.args[1],
        RuntimeError,
    )


@pytest.mark.asyncio
async def test_on_after_account_restore(user_manager, user):
    with patch(
        "app.services.user_manager.send_email",
        new_callable=AsyncMock,
    ) as send_email_mock:
        await user_manager.on_after_account_restore(user)

    send_email_mock.assert_awaited_once()

    args, kwargs = send_email_mock.call_args

    assert args[0] == user.email
    assert args[1] == "Аккаунт успешно восстановлен"
    assert "Ваш аккаунт в сервисе «3шагадо» успешно восстановлен." in args[2]
    assert "изменить пароль" in args[2]
    assert kwargs["html"] is True
