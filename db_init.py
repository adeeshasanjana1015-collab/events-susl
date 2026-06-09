# events_susl_hermes/db_init.py
"""Initialize the MySQL database and create all tables."""

import MySQLdb
from config import Config

def init_db():
    conn = MySQLdb.connect(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD
    )
    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {Config.MYSQL_DB} "
                   f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute(f"USE {Config.MYSQL_DB}")

    # ---------- admins ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(150) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB
    """)

    # ---------- categories ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(80) UNIQUE NOT NULL
    ) ENGINE=InnoDB
    """)

    # ---------- venues ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS venues (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        type VARCHAR(80),
        location VARCHAR(200),
        capacity INT DEFAULT 0
    ) ENGINE=InnoDB
    """)

    # ---------- events ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(200) NOT NULL,
        description TEXT,
        category_id INT,
        venue_id INT,
        event_date DATE NOT NULL,
        event_time TIME NOT NULL,
        capacity INT DEFAULT 100,
        image VARCHAR(255) DEFAULT 'default_event.jpg',
        status VARCHAR(20) DEFAULT 'Available',
        registration_open TINYINT DEFAULT 1,
        registration_close_date DATE,
        registration_close_time TIME,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
        FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE SET NULL
    ) ENGINE=InnoDB
    """)

    # ---------- registrations ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registrations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_id INT NOT NULL,
        registration_number INT DEFAULT 0,
        full_name VARCHAR(150) NOT NULL,
        email VARCHAR(150) NOT NULL,
        phone VARCHAR(20),
        student_id VARCHAR(50),
        department VARCHAR(150),
        qr_code VARCHAR(255),
        status VARCHAR(20) DEFAULT 'Active',
        attendance_status TINYINT DEFAULT 0,
        check_in_time TIMESTAMP NULL,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """)

    # ---------- attendance ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        registration_id INT NOT NULL,
        event_id INT NOT NULL,
        check_in_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (registration_id) REFERENCES registrations(id) ON DELETE CASCADE,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """)

    # ---------- feedback ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_id INT NOT NULL,
        registration_id INT,
        rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
        comment TEXT,
        is_deleted TINYINT DEFAULT 0,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (registration_id) REFERENCES registrations(id) ON DELETE SET NULL
    ) ENGINE=InnoDB
    """)

    # ---------- event_media ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_media (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_id INT NOT NULL,
        media_type VARCHAR(20) NOT NULL,
        filename VARCHAR(255),
        url VARCHAR(500),
        caption VARCHAR(255),
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """)

    # ---------- add missing columns to existing tables (safe ALTER) ----------
    for col, ddl in [
        ('registration_open', "ALTER TABLE events ADD COLUMN registration_open TINYINT DEFAULT 1"),
        ('registration_close_date', "ALTER TABLE events ADD COLUMN registration_close_date DATE"),
        ('registration_close_time', "ALTER TABLE events ADD COLUMN registration_close_time TIME"),
        ('registration_number', "ALTER TABLE registrations ADD COLUMN registration_number INT DEFAULT 0"),
        ('status', "ALTER TABLE registrations ADD COLUMN status VARCHAR(20) DEFAULT 'Active'"),
        ('removed_at', "ALTER TABLE registrations ADD COLUMN removed_at TIMESTAMP NULL"),
        ('restored_at', "ALTER TABLE registrations ADD COLUMN restored_at TIMESTAMP NULL"),
    ]:
        try:
            cursor.execute(ddl)
        except MySQLdb.OperationalError:
            pass  # column already exists

    conn.commit()
    cursor.close()
    conn.close()
    print("Database and tables created successfully!")

if __name__ == "__main__":
    init_db()
