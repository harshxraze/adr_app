import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'adr-causality-secret-key-2026')

    # Database: support PostgreSQL (Supabase) via DATABASE_URL env var, fallback to SQLite
    db_url = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "adr_database.db")}')
    # Heroku/Supabase sometimes uses postgres:// which SQLAlchemy doesn't accept
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    # Strip ?pgbouncer=true — psycopg2 doesn't recognize it as a valid option
    db_url = db_url.replace('?pgbouncer=true', '').replace('&pgbouncer=true', '')
    SQLALCHEMY_DATABASE_URI = db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
