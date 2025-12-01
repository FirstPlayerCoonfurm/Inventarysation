FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    postgresql-client \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app
WORKDIR /home/app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY --chown=app:app . .

# Переключаемся на непривилегированного пользователя
USER app

# Создаем папку для логов
RUN mkdir -p logs

# Открываем порт
EXPOSE 5000

# Запускаем приложение
CMD ["python", "app.py"]
