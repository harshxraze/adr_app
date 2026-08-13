import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # SECURITY: fail-fast if SECRET_KEY is not set — prevents silent weak-key
    # issues on Render cold starts. Set it as a persistent env var.
    SECRET_KEY = os.environ['SECRET_KEY']

    # ---------- Persistent session / remember-me (PWA friendly) ----------
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)
    REMEMBER_COOKIE_DURATION = timedelta(days=365)
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
    REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Seeded admin account configuration. Passwords must come from env only.
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
    ADMIN_DISPLAY_NAME = os.environ.get('ADMIN_DISPLAY_NAME', 'ADR Administrator')
    ADMIN_DEPARTMENT = os.environ.get('ADMIN_DEPARTMENT', 'Pharmacovigilance Unit')

    db_url = os.environ.get('DATABASE_URL')
    
    has_psycopg2 = False
    try:
        import psycopg2
        has_psycopg2 = True
    except ImportError:
        pass

    if not db_url or not has_psycopg2:
        db_url = f'sqlite:///{os.path.join(BASE_DIR, "adr_database.db")}'

    # Heroku/Supabase sometimes uses postgres:// which SQLAlchemy doesn't accept
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    # Strip ?pgbouncer=true — psycopg2 doesn't recognize it as a valid option
    db_url = db_url.replace('?pgbouncer=true', '').replace('&pgbouncer=true', '')
    SQLALCHEMY_DATABASE_URI = db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
