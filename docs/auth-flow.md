# Логин, логаут и токены

Этот документ описывает работу access token и refresh token.

## Общая схема

- access token - JWT;
- refresh token - случайная строка, хранимая в БД;
- оба токена передаются через `HttpOnly` cookies;
- при логине создаётся новая refresh-сессия;
- при логауте refresh token удаляется из БД и из cookies.

## Login

`POST /api/auth/login`

После успешной аутентификации:

- создаётся access token;
- создаётся refresh token;
- оба токена возвращаются в cookies.

## Logout

`POST /api/auth/logout`

При выходе:

- access cookie очищается;
- refresh cookie очищается;
- refresh token удаляется из БД.

## Refresh token

Refresh token хранится в таблице `refresh_tokens` и связан с пользователем через `user_id`.

В сервисе реализованы операции:

- удаление текущего token;
- удаление всех token пользователя;
- создание нового token при логине.

## Cookie-параметры

Параметры cookie задаются в `CookieTransportCustom`:

- access token cookie name - `access_token`;
- refresh token cookie name берётся из настроек;
- access cookie path - `/`;
- refresh cookie path берётся из настроек;
- `HttpOnly` включён;
- `Secure` зависит от режима debug.

## Что важно знать

- access token используется для авторизации запросов;
- refresh token нужен только для обновления доступа и выхода;
- после смены пароля refresh token пользователя удаляются, чтобы старые сессии не оставались активными.

