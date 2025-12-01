import os
import secrets
from dotenv import load_dotenv

def generate_secret_key():
    """Генерирует случайный секретный ключ"""
    return secrets.token_hex(32)

def setup_environment():
    """Настраивает окружение и SECRET_KEY"""
    env_file = '.env'

    # В Docker используем переменные окружения, в разработке - .env файл
    if not os.environ.get('DB_HOST') and os.path.exists(env_file):
        load_dotenv()

    # Проверяем SECRET_KEY
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        secret_key = generate_secret_key()
        # В продакшне это должно быть установлено через переменные окружения
        print("⚠️  ВНИМАНИЕ: Используется временный SECRET_KEY. Для продакшна установите SECRET_KEY в переменных окружения")

    return secret_key

class Config:
    # Секретный ключ
    SECRET_KEY = setup_environment()

    # PostgreSQL configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'it_inventory')
    DB_USER = os.environ.get('DB_USER', 'it_user')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'password')

    SQLALCHEMY_DATABASE_URI = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Настройки для Docker
    @classmethod
    def check_database_connection(cls):
        """Проверяет доступность базы данных"""
        try:
            import psycopg2
            conn = psycopg2.connect(
                dbname=cls.DB_NAME,
                user=cls.DB_USER,
                password=cls.DB_PASSWORD,
                host=cls.DB_HOST,
                port=cls.DB_PORT,
                connect_timeout=5  # Таймаут 5 секунд
            )
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к базе данных: {e}")
            return False
