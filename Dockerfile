FROM python:3.11-slim

WORKDIR /code

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Команда по умолчанию (будет переопределена в docker-compose для разработки)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]