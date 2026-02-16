import logging
import os
import sys
from typing import List

import pytest

# Обеспечиваем импорт пакета app при запуске тестов
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.services.email import send_email  # noqa: E402
from config import settings  # noqa: E402


@pytest.mark.asyncio
async def test_send_email_debug_mode_logs_only(caplog):
    """При DEBUG=true письмо не отправляется, только логируется."""
    # given
    settings.debug = True
    settings.mail_server = "smtp.example.com"
    settings.mail_from = "from@example.com"

    with caplog.at_level(logging.INFO):
        # when
        await send_email("user@example.com", "Subject", "Body")

    # then
    messages: List[str] = [record.getMessage() for record in caplog.records]
    assert any("Email DEBUG mode. Письмо НЕ отправлено" in m for m in messages)


@pytest.mark.asyncio
async def test_send_email_missing_config_logs_warning(caplog):
    """Если настройки почты не заданы, письмо не отправляется и пишется warning."""
    # given
    settings.debug = False
    settings.mail_server = ""
    settings.mail_from = ""

    with caplog.at_level(logging.WARNING):
        # when
        await send_email("user@example.com", "Subject", "Body")

    # then
    messages: List[str] = [record.getMessage() for record in caplog.records]
    assert any("Email settings are not configured" in m for m in messages)


@pytest.mark.asyncio
async def test_send_email_sends_with_valid_config(monkeypatch):
    """При валидной конфигурации отправка делегируется FastMail."""
    # given
    settings.debug = False
    settings.mail_server = "smtp.example.com"
    settings.mail_from = "from@example.com"
    settings.mail_username = "user"
    settings.mail_password = "pass"

    sent_messages = []

    class DummyFastMail:
        def __init__(self, *args, **kwargs):
            pass

        async def send_message(self, message):
            sent_messages.append(message)

    # monkeypatch FastMail внутри модуля email
    import app.services.email as email_module

    monkeypatch.setattr(email_module, "FastMail", DummyFastMail)

    # when
    await send_email("user@example.com", "Subject", "Body")

    # then
    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg.subject == "Subject"
    assert "user@example.com" in msg.recipients
