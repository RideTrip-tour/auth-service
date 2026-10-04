from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.audit as audit_service


def test_extract_request_details_without_request():
    result = audit_service._extract_request_details(None)
    assert result == {}


@pytest.mark.parametrize(
    ("method", "expected_method"),
    [
        ("post", "POST"),
        (None, None),
    ],
)
def test_extract_request_details(method, expected_method):
    request = SimpleNamespace(
        headers={
            "x-forwarded-for": " 192.168.1.10, 10.0.0.1",
            "user-agent": "TestAgent/1.0",
        },
        client=SimpleNamespace(host="127.0.0.1"),
        method=method,
        url=SimpleNamespace(path="/api/auth/login"),
    )

    result = audit_service._extract_request_details(request)

    assert result == {
        "method": expected_method,
        "path": "/api/auth/login",
        "ip_address": "192.168.1.10",
        "user_agent": "TestAgent/1.0",
    }


@pytest.mark.asyncio
async def test_log_event_success(mocker):
    session = MagicMock()

    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)

    transaction_context = MagicMock()
    transaction_context.__aenter__ = AsyncMock(return_value=session)
    transaction_context.__aexit__ = AsyncMock(return_value=None)

    session.begin.return_value = transaction_context

    mocker.patch(
        "app.services.audit.AsyncSessionLocal",
        return_value=session_context,
    )

    request = SimpleNamespace(
        headers={
            "x-forwarded-for": "1.2.3.4",
            "user-agent": "pytest",
        },
        client=SimpleNamespace(host="127.0.0.1"),
        method="post",
        url=SimpleNamespace(path="/api/test"),
    )

    await audit_service.log_event(
        audit_service.AuditEventType.LOGIN_SUCCESS,
        request=request,
        user_id=42,
        details={"foo": "bar"},
    )

    session.add.assert_called_once()

    log_entry = session.add.call_args.args[0]

    assert log_entry.event_type == audit_service.AuditEventType.LOGIN_SUCCESS
    assert log_entry.user_id == 42
    assert log_entry.success is True
    assert log_entry.reason is None
    assert log_entry.details == {
        "method": "POST",
        "path": "/api/test",
        "ip_address": "1.2.3.4",
        "user_agent": "pytest",
        "foo": "bar",
    }
