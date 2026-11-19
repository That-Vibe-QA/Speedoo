import os
import tempfile

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-speedoo-secret-key-replace-me')
    
    # In Vercel serverless functions, the root filesystem is read-only.
    # If DATABASE_URL is not set or defaults to a local file, store it in /tmp on serverless environments.
    default_db_path = os.path.join(tempfile.gettempdir(), 'speedoo.db') if os.environ.get('VERCEL') else 'speedoo.db'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{default_db_path}')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    # Security options
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    WTF_CSRF_TIME_LIMIT = 3600

