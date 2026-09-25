# Описание API

Базовый URL: **http://localhost:8000**

Интерактивная документация (Swagger UI): **http://localhost:8000/docs**  
Альтернативная (ReDoc): **http://localhost:8000/redoc**

---

## Аутентификация

Проект использует **JWT** (Bearer-токены).  
Формат передачи: HTTP-заголовок `Authorization: Bearer <token>`.

### POST /auth/login

Получить JWT-токен.

**Формат запроса:** `application/x-www-form-urlencoded`

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `username` | string | да | Логин пользователя |
| `password` | string | да | Пароль |

**Пример:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"