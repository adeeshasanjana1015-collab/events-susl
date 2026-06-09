# events_susl_hermes/config.py
import os

def _env(*keys):
    """Return the first environment variable that is set (non-empty), or None."""
    for k in keys:
        val = os.environ.get(k)
        if val:  # catches None and empty string
            return val
    return None


class Config:
    SECRET_KEY = _env('SECRET_KEY') or 'events-susl-secret-key-2026'

    # MySQL host — Railway auto: MYSQLHOST, manual: DB_HOST, local: MYSQL_HOST
    MYSQL_HOST = _env('MYSQLHOST', 'DB_HOST', 'MYSQL_HOST') or 'localhost'

    # MySQL port — Railway auto: MYSQLPORT, manual: DB_PORT, default 3306
    MYSQL_PORT = int(_env('MYSQLPORT', 'DB_PORT') or 3306)

    # MySQL user — Railway auto: MYSQLUSER, manual: DB_USER, local: MYSQL_USER
    MYSQL_USER = _env('MYSQLUSER', 'DB_USER', 'MYSQL_USER') or 'root'

    # MySQL password — Railway auto: MYSQLPASSWORD, manual: DB_PASSWORD, local: MYSQL_PASSWORD
    MYSQL_PASSWORD = _env('MYSQLPASSWORD', 'DB_PASSWORD', 'MYSQL_PASSWORD') or ''

    # MySQL database — Railway auto: MYSQLDATABASE, manual: DB_NAME, local: MYSQL_DB
    MYSQL_DB = _env('MYSQLDATABASE', 'DB_NAME', 'MYSQL_DB') or 'events_susl'

    MYSQL_CURSORCLASS = 'DictCursor'
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
    QR_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'qrcodes')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
