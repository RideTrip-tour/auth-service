import logging
from typing import Iterable, List, Union

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import EmailStr

from config import settings

logger = logging.getLogger("email")


async def send_email(
    to: Union[EmailStr, str, Iterable[Union[EmailStr, str]]],
    subject: str,
    body: str,
    *,
    html: bool = True,
) -> None:
    """Отправка письма пользователю.

    Поведение:
      - если DEBUG=true, письмо не отправляется, а выводится в лог/консоль;
      - если почтовые настройки не заданы, пишем в лог и ничего не делаем;
      - иначе отправляем письмо через SMTP.
    """

    if isinstance(to, (str, EmailStr)):
        recipients: List[Union[EmailStr, str]] = [to]
    else:
        recipients = list(to)

    # Тестовый режим – просто логируем письмо
    if settings.debug:
        logger.info(
            "Email DEBUG mode. Письмо НЕ отправлено.\nTo: %s\nSubject: %s\nBody:\n%s",
            ", ".join(map(str, recipients)),
            subject,
            body,
        )
        logger.error("Зашли в отправку почты")
        return

    # Проверяем, что базовые настройки почты заданы
    if not settings.mail_server or not settings.mail_from:

        logger.warning(
            "Email settings are not configured (MAIL_SERVER / MAIL_FROM). "
            "Письмо не будет отправлено."
        )
        return

    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype=MessageType.html if html else MessageType.plain,
    )

    try:
        conf = ConnectionConfig(
            MAIL_USERNAME=settings.mail_username,
            MAIL_PASSWORD=settings.mail_password,
            MAIL_FROM=settings.mail_from,
            MAIL_FROM_NAME=settings.mail_from_name,
            MAIL_SERVER=settings.mail_server,
            MAIL_PORT=settings.mail_port,
            MAIL_STARTTLS=settings.mail_starttls,
            MAIL_SSL_TLS=settings.mail_ssl_tls,
            USE_CREDENTIALS=bool(settings.mail_username and settings.mail_password),
        )

        fast_mail = FastMail(conf)
        await fast_mail.send_message(message)
    except Exception as exc:
        logger.exception("Ошибка при отправке email: %s", exc)
