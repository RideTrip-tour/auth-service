# Cookie policy

Сервис хранит токены авторизации в cookies, чтобы браузер отправлял их автоматически.

## Какие cookie используются

- `access_token` - JWT access token;
- refresh token cookie - значение берётся из настроек сервиса;
- обе cookie устанавливаются как `HttpOnly`.

## Назначение cookie

- `access_token` используется для доступа к защищённым API;
- refresh token нужен для продления сессии и удаления старых сессий;
- access token живёт меньше, чем refresh token.

## Параметры access cookie

- `HttpOnly = true`;
- `Secure = true` в production, иначе выключен;
- `SameSite = Lax`;
- `Path = /`;
- `Max-Age` берётся из настроек access token.

## Параметры refresh cookie

- `HttpOnly = true`;
- `Secure = true` в production, иначе выключен;
- `SameSite = Lax`;
- `Path` берётся из настроек сервиса;
- `Max-Age` берётся из настроек refresh token;
- значение связано с записью в таблице `refresh_tokens`.

## Когда cookie удаляются

- при `POST /api/auth/logout`;
- при смене пароля пользователя;
- при ручной очистке сессий на стороне сервера.

## Практический смысл

Такой подход позволяет:

- не хранить токены в localStorage;
- уменьшить риск доступа к токенам через JavaScript;
- централизованно отзывать refresh token через БД;
- инвалидировать старые сессии после критичных операций.
