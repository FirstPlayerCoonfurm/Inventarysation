FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости, включая инструменты для сборки
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
