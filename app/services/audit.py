import logging
from typing import Any

from fastapi import Request

from app.db.database import AsyncSessionLocal
from app.db.models import UserActionLog

logger = logging.getLogger("audit")


class AuditEventType:
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    SESSION_CREATED = "session_created"
    SESSION_ROTATED = "session_rotated"
    SESSION_ROTATE_FAILED = "session_rotate_failed"
    LOGOUT = "logout"
    CHANGE_REQUESTED = "change_requested"
    CHANGE_FAILED = "change_failed"
    CHANGE_COMPLETED = "change_completed"
    REGISTERED = "registered"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    VERIFICATION_REQUESTED = "verification_requested"


def _extract_request_details(request: Request | None) -> dict[str, Any]:
    if request is None:
        return {}

    headers = getattr(request, "headers", {}) or {}
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        client = getattr(request, "client", None)
        ip_address = getattr(client, "host", None)

    method = getattr(request, "method", None)
    if isinstance(method, str):
        method = method.upper()
    else:
        method = None

    return {
        "method": method,
        "path": getattr(getattr(request, "url", None), "path", None),
        "ip_address": ip_address,
        "user_agent": headers.get("user-agent"),
    }


async def log_event(
    event_type: str,
    *,
    request: Request | None = None,
    user_id: int | None = None,
    success: bool = True,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    payload = _extract_request_details(request)
    if details:
        payload.update(details)

    try:
        async with AsyncSessionLocal() as session, session.begin():
            session.add(
                UserActionLog(
                    event_type=event_type,
                    user_id=user_id,
                    success=success,
                    reason=reason,
                    details=payload or None,
                )
            )
    except Exception:
        logger.exception("Failed to persist audit event %s", event_type)
