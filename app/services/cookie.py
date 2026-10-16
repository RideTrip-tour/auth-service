import logging

from fastapi import Response, status
from fastapi_users.authentication import CookieTransport

from config import settings

logger = logging.getLogger(__name__)


class CookieTransportCustom(CookieTransport):
    refresh_token_name = settings.refresh_token_name
    access_cookie_max_age = settings.access_token_expire_sec
    refresh_cookie_max_age = settings.refresh_token_expire_sec
    refresh_cookie_path = settings.refresh_token_path
    access_cookie_path = "/"

    async def get_login_response(
        self,
        access_token: str,
        refresh_token: str | None = None,
    ) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response = self._set_access_cookie(response, access_token)
        if refresh_token:
            response = self._set_refresh_cookie(response, refresh_token)
        else:
            logger.warning("Refresh token не установлен!")
        return response

    async def get_logout_response(self) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        self._clear_access_cookie(response)
        self._clear_refresh_cookie(response)
        return response

    def _set_refresh_cookie(self, response, refresh_token):
        logger.info(
            f"Установка {self.refresh_token_name} cookie: path={self.refresh_cookie_path}"
        )
        response.set_cookie(
            key=self.refresh_token_name,
            value=refresh_token,
            httponly=True,
            secure=not settings.debug,
            samesite="lax",
            max_age=self.refresh_cookie_max_age,
            path=self.refresh_cookie_path,
        )
        logger.info("Установлен refresh token")
        return response

    def _set_access_cookie(self, response: Response, token: str) -> Response:
        logger.info(
            f"Установка {self.cookie_name} cookie: path={self.access_cookie_path}"
        )
        response.set_cookie(
            key=self.cookie_name,
            value=token,
            max_age=self.access_cookie_max_age,
            path=self.access_cookie_path,
            secure=not settings.debug,
            httponly=True,
            samesite=self.cookie_samesite,
        )
        return response

    def _clear_access_cookie(self, response: Response) -> None:
        response.set_cookie(
            key=self.cookie_name,
            value="",
            max_age=0,
            path=self.access_cookie_path,
            domain=self.cookie_domain,
            secure=not settings.debug,
            httponly=True,
            samesite=self.cookie_samesite,
        )

    def _clear_refresh_cookie(self, response: Response) -> None:
        response.set_cookie(
            key=self.refresh_token_name,
            value="",
            httponly=True,
            secure=not settings.debug,
            samesite="lax",
            max_age=0,
            path=self.refresh_cookie_path,
        )


cookie_transport = CookieTransportCustom(
    cookie_name="access_token",
    cookie_max_age=settings.access_token_expire_sec,
)
