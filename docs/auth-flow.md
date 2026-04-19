# Логин, логаут и токены

Этот документ описывает работу access token и refresh token.

Отдельно сервис пишет audit-события в таблицу `user_action_logs`:

- `login_success` и `login_failed`;
- `session_created`, `session_rotated` и `session_rotate_failed`;
- `logout`;
- `change_requested`, `change_failed`, `change_completed` для смены пароля и email;
- в `details.change_type` хранится `password` или `email`.

Для каждого события сохраняются:

- `event_type` - тип действия;
- `user_id` - id пользователя, если он известен;
- `success` - успешность события;
- `reason` - краткая причина для неуспешных случаев;
- `details` - дополнительный контекст события;
- `created_at` - время записи события в БД.

В `details` дополнительно попадают данные запроса:

- `method` и `path`;
- `ip_address`, если его можно определить;
- `user_agent`, если он есть;
- любые прикладные поля события, например `change_type`, `current_email`, `new_email` или `refresh_token_id`.

IP-адрес берется из заголовка, который нормализует gateway. Пользовательский `X-Forwarded-For` напрямую downstream не использует.

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
