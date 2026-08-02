from fastapi import Request
from fastapi.responses import JSONResponse

from config import settings


async def limit_login_form_body(request: Request, call_next):
    if request.url.path == "/api/auth/login":
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
        if content_type == "application/x-www-form-urlencoded":
            content_length = request.headers.get("content-length")
            if content_length is None:
                return JSONResponse(
                    status_code=411,
                    content={"detail": "Content-Length required"},
                )
            try:
                body_size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length"},
                )
            if body_size > settings.login_form_max_body_size:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Login form body too large"},
                )

    return await call_next(request)
