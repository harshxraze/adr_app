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
    
    has_psycopg = False
    has_psycopg2 = False
    try:
        import psycopg
        has_psycopg = True
    except ImportError:
        pass

    try:
        import psycopg2
        has_psycopg2 = True
    except ImportError:
        pass

    if not db_url or (not has_psycopg and not has_psycopg2):
        db_url = f'sqlite:///{os.path.join(BASE_DIR, "adr_database.db")}'
    else:
        # Heroku/Render/Supabase often sets postgres:// which SQLAlchemy rejects
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)

        # Match URL scheme with available driver
        if db_url.startswith('postgresql+psycopg://') and not has_psycopg and has_psycopg2:
            # Fall back to psycopg2 if psycopg 3 is missing
            db_url = db_url.replace('postgresql+psycopg://', 'postgresql+psycopg2://', 1)
        elif db_url.startswith(('postgresql://', 'postgresql+psycopg2://')) and has_psycopg and not has_psycopg2:
            # Upgrade to psycopg 3 driver if psycopg2 is missing
            if db_url.startswith('postgresql://'):
                db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
            else:
                db_url = db_url.replace('postgresql+psycopg2://', 'postgresql+psycopg://', 1)
        elif db_url.startswith('postgresql://') and has_psycopg:
            # Prefer modern psycopg 3 driver for PostgreSQL
            db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)

        # Strip ?pgbouncer=true — drivers don't recognize it as a valid connection parameter
        db_url = db_url.replace('?pgbouncer=true', '').replace('&pgbouncer=true', '')

    SQLALCHEMY_DATABASE_URI = db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
