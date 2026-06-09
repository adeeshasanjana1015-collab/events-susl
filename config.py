# events_susl_hermes/config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'events-susl-secret-key-2026')

    # MySQL host — Railway uses MYSQLHOST, local uses MYSQL_HOST
    MYSQL_HOST = os.environ.get('MYSQLHOST') or os.environ.get('MYSQL_HOST', 'localhost')

    # MySQL port — Railway uses MYSQLPORT
    MYSQL_PORT = int(os.environ.get('MYSQLPORT', 3306))

    # MySQL user — Railway uses MYSQLUSER, local uses MYSQL_USER
    MYSQL_USER = os.environ.get('MYSQLUSER') or os.environ.get('MYSQL_USER', 'root')

    # MySQL password — Railway uses MYSQLPASSWORD, local uses MYSQL_PASSWORD
    MYSQL_PASSWORD = os.environ.get('MYSQLPASSWORD') or os.environ.get('MYSQL_PASSWORD', '')

    # MySQL database — Railway uses MYSQLDATABASE, local uses MYSQL_DB
    MYSQL_DB = os.environ.get('MYSQLDATABASE') or os.environ.get('MYSQL_DB', 'events_susl')

    MYSQL_CURSORCLASS = 'DictCursor'
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
    QR_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'qrcodes')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
