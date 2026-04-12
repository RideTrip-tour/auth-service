# Сервис аутентификации

Сервис отвечает за регистрацию, вход, выход, верификацию пользователей и управление сессиями в проекте `trip-constructor`.

Он построен на FastAPI и `fastapi-users`, а для хранения refresh token использует отдельную таблицу в PostgreSQL.

## Возможности

- регистрация пользователей по email и паролю;
- подтверждение регистрации по email;
- вход и выход через JWT access token и refresh token в cookies;
- сброс и смена пароля;
- запрос смены email с подтверждением по ссылке;
- OAuth2-вход через внешнего провайдера;
- защищённые эндпоинты для авторизованных пользователей.

## Быстрый старт

### 1. Установка зависимостей

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка окружения

Создайте `.env` по образцу `.env.example` и заполните параметры базы данных, JWT и почты.

### 3. Применение миграций

```bash
alembic upgrade head
```

### 4. Запуск сервиса

```bash
uvicorn main:app --reload
```

После запуска API будет доступен на `http://127.0.0.1:8000`.

## Что где лежит

- [`app/services/users.py`](app/services/users.py) - сборка пользовательского менеджера, JWT-стратегии и auth backend;
- [`app/routes/register.py`](app/routes/register.py) - маршруты регистрации и верификации;
- [`app/routes/auth.py`](app/routes/auth.py) - login/logout;
- [`app/routes/users.py`](app/routes/users.py) - пользовательские операции над текущим аккаунтом;
- [`app/db/models.py`](app/db/models.py) - таблицы пользователей и refresh token;
- [`app/schemas/users.py`](app/schemas/users.py) - Pydantic-схемы запросов и ответов.

## Модель данных

Основные сущности:

- `User` - аккаунт пользователя, JWT/верификация завязаны на email, пароль и флаги активности;
- `OAuthAccount` - привязанные OAuth-аккаунты;
- `RefreshToken` - refresh token, сохранённый в БД и связанный с пользователем.

Подробности по токенам, верификации и пользовательским эндпоинтам вынесены в отдельные файлы:

- [`docs/registration-verification.md`](docs/registration-verification.md)
- [`docs/auth-flow.md`](docs/auth-flow.md)
- [`docs/cookie-policy.md`](docs/cookie-policy.md)
- [`docs/user-management.md`](docs/user-management.md)

## Cookie policy

Сервис использует два HttpOnly cookie:

- `access_token` - короткоживущий JWT для авторизации API-запросов;
- refresh token cookie - хранится отдельно и используется для обновления сессии и logout.

Параметры cookie зависят от режима запуска и настроек сервиса:

- `HttpOnly` включён;
- `Secure` включается в production;
- для access и refresh cookie используются разные `path`;
- refresh token привязан к БД и удаляется при logout и смене пароля.

## Тесты

```bash
DEBUG=false python -m pytest -q
```
