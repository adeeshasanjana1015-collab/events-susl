import os
from datetime import datetime, date, time
import MySQLdb
import bcrypt
import qrcode

# -----------------------------
# Database configuration (reads from environment)
# -----------------------------
def _env(*keys):
    """Return the first environment variable that is set (non-empty), or None."""
    for k in keys:
        val = os.environ.get(k)
        if val:
            return val
    return None

DB_HOST = _env('MYSQLHOST', 'DB_HOST', 'MYSQL_HOST') or 'localhost'
DB_PORT = int(_env('MYSQLPORT', 'DB_PORT') or 3306)
DB_USER = _env('MYSQLUSER', 'DB_USER', 'MYSQL_USER') or 'root'
DB_PASSWORD = _env('MYSQLPASSWORD', 'DB_PASSWORD', 'MYSQL_PASSWORD') or ''
DB_NAME = _env('MYSQLDATABASE', 'DB_NAME', 'MYSQL_DB') or 'events_susl'


def get_connection():
    return MySQLdb.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        passwd=DB_PASSWORD,
        db=DB_NAME
    )


def generate_qr_image(qr_code_value):
    qrcode_folder = os.path.join("static", "qrcodes")
    os.makedirs(qrcode_folder, exist_ok=True)

    filename = f"{qr_code_value}.png"
    filepath = os.path.join(qrcode_folder, filename)

    img = qrcode.make(qr_code_value)
    img.save(filepath)

    return filename


def clear_existing_data(cursor, conn):
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    cursor.execute("DELETE FROM attendance")
    cursor.execute("DELETE FROM registrations")
    cursor.execute("DELETE FROM events")
    cursor.execute("DELETE FROM venues")
    cursor.execute("DELETE FROM categories")
    cursor.execute("DELETE FROM admins")

    cursor.execute("ALTER TABLE attendance AUTO_INCREMENT = 1")
    cursor.execute("ALTER TABLE registrations AUTO_INCREMENT = 1")
    cursor.execute("ALTER TABLE events AUTO_INCREMENT = 1")
    cursor.execute("ALTER TABLE venues AUTO_INCREMENT = 1")
    cursor.execute("ALTER TABLE categories AUTO_INCREMENT = 1")
    cursor.execute("ALTER TABLE admins AUTO_INCREMENT = 1")

    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()


def seed_admin(cursor):
    password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    cursor.execute("""
        INSERT INTO admins (name, email, password_hash)
        VALUES (%s, %s, %s)
    """, ("Admin", "admin@gmail.com", password_hash))

    print("Admin seeded.")


def seed_categories(cursor):
    categories = [
        "Music",
        "Sports",
        "Workshop",
        "Seminar",
        "Cultural",
        "Tech Event",
        "Other"
    ]

    for category in categories:
        cursor.execute("""
            INSERT INTO categories (name)
            VALUES (%s)
        """, (category,))

    print("7 categories seeded.")


def seed_venues(cursor):
    venues = [
        ("Main Auditorium", "Auditorium", "University Premises", 500),
        ("University Main Hall", "Hall", "University Premises", 300),
        ("Faculty Auditorium", "Auditorium", "Faculty Area", 250),
        ("Management Faculty Hall", "Hall", "Management Faculty", 180),
        ("Social Sciences and Languages Hall", "Hall", "SSL Faculty", 180),
        ("Applied Sciences Lecture Hall", "Lecture Hall", "Applied Sciences Faculty", 120),
        ("Faculty of Computing Lab", "Computer Lab", "Faculty of Computing", 80),
        ("Computer Lab 01", "Computer Lab", "Faculty of Computing", 60),
        ("University Playground", "Ground", "Sports Area", 1000),
        ("University Playground Pavilion", "Pavilion", "Sports Area", 300),
        ("Indoor Sports Complex", "Sports Complex", "Sports Area", 400),
        ("Sports Court", "Court", "Sports Area", 150),
        ("Open Ground", "Ground", "University Premises", 1200),
        ("Seminar Room 01", "Seminar Room", "Faculty Area", 70),
        ("Conference Hall", "Conference Hall", "Administration Area", 100)
    ]

    for venue in venues:
        cursor.execute("""
            INSERT INTO venues (name, type, location, capacity)
            VALUES (%s, %s, %s, %s)
        """, venue)

    print("15 venues seeded.")


def get_category_id(cursor, category_name):
    cursor.execute("""
        SELECT id FROM categories
        WHERE name = %s
        LIMIT 1
    """, (category_name,))
    result = cursor.fetchone()
    return result[0] if result else None


def get_venue_id(cursor, venue_name):
    cursor.execute("""
        SELECT id FROM venues
        WHERE name = %s
        LIMIT 1
    """, (venue_name,))
    result = cursor.fetchone()
    return result[0] if result else None


def seed_events(cursor):
    events = [
        {
            "title": "Music Night",
            "description": "A university music event featuring student performances, bands, and entertainment activities.",
            "category": "Music",
            "venue": "University Main Hall",
            "date": date(2026, 7, 10),
            "time": time(18, 0),
            "location": "University Main Hall",
            "capacity": 300,
            "image": "music-night.jpg",
            "status": "Available"
        },
        {
            "title": "Tech Workshop",
            "description": "A hands-on technology workshop for students interested in software development and innovation.",
            "category": "Tech Event",
            "venue": "Faculty of Computing Lab",
            "date": date(2026, 7, 15),
            "time": time(9, 30),
            "location": "Faculty of Computing",
            "capacity": 80,
            "image": "tech-workshop.jpg",
            "status": "Available"
        },
        {
            "title": "Sports Meet",
            "description": "A university sports event with athletic activities, team games, and student participation.",
            "category": "Sports",
            "venue": "University Playground",
            "date": date(2026, 7, 20),
            "time": time(8, 0),
            "location": "University Playground",
            "capacity": 1000,
            "image": "sports-meet.jpg",
            "status": "Available"
        },
        {
            "title": "Cultural Festival",
            "description": "A cultural event celebrating student talents, traditional performances, and university diversity.",
            "category": "Cultural",
            "venue": "Main Auditorium",
            "date": date(2026, 8, 5),
            "time": time(17, 0),
            "location": "Main Auditorium",
            "capacity": 500,
            "image": "cultural-festival.jpg",
            "status": "Available"
        },
        {
            "title": "Data Science Seminar",
            "description": "A seminar for data science students covering analytics, machine learning, and career opportunities.",
            "category": "Seminar",
            "venue": "Conference Hall",
            "date": date(2026, 8, 12),
            "time": time(10, 0),
            "location": "Conference Hall",
            "capacity": 100,
            "image": "data-science.jpg",
            "status": "Available"
        },
        {
            "title": "Career Guidance Session",
            "description": "A career guidance session for students to learn about internships, job opportunities, and professional skills.",
            "category": "Workshop",
            "venue": "Seminar Room 01",
            "date": date(2026, 8, 18),
            "time": time(13, 30),
            "location": "Seminar Room 01",
            "capacity": 70,
            "image": "career-guidance.jpg",
            "status": "Available"
        }
    ]

    for event in events:
        category_id = get_category_id(cursor, event["category"])
        venue_id = get_venue_id(cursor, event["venue"])

        cursor.execute("""
            INSERT INTO events
            (category_id, venue_id, title, description, event_date, event_time, capacity, image, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            category_id,
            venue_id,
            event["title"],
            event["description"],
            event["date"],
            event["time"],
            event["capacity"],
            event["image"],
            event["status"]
        ))

    print("6 events seeded.")


def get_event_id(cursor, event_title):
    cursor.execute("""
        SELECT id FROM events
        WHERE title = %s
        LIMIT 1
    """, (event_title,))
    result = cursor.fetchone()
    return result[0] if result else None


def seed_registrations(cursor):
    registrations = [
        {
            "event": "Music Night",
            "participant_name": "Kasun Perera",
            "email": "kasun@example.com",
            "phone": "0771234567",
            "student_id": "DS2026001",
            "department": "Data Science"
        },
        {
            "event": "Tech Workshop",
            "participant_name": "Nimal Fernando",
            "email": "nimal@example.com",
            "phone": "0772345678",
            "student_id": "DS2026002",
            "department": "Computing"
        },
        {
            "event": "Data Science Seminar",
            "participant_name": "Ayesha Silva",
            "email": "ayesha@example.com",
            "phone": "0773456789",
            "student_id": "DS2026003",
            "department": "Data Science"
        }
    ]

    for index, reg in enumerate(registrations, start=1):
        event_id = get_event_id(cursor, reg["event"])
        qr_code_value = f"EVENTS_SUSL_QR_{event_id}_{index}_{int(datetime.now().timestamp())}"

        generate_qr_image(qr_code_value)

        cursor.execute("""
            INSERT INTO registrations
            (event_id, registration_number, full_name, email, phone, student_id, department, registered_at, qr_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """, (
            event_id,
            index,
            reg["participant_name"],
            reg["email"],
            reg["phone"],
            reg["student_id"],
            reg["department"],
            qr_code_value
        ))

    print("3 sample registrations seeded.")


def main():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        clear_existing_data(cursor, conn)

        seed_admin(cursor)
        seed_categories(cursor)
        seed_venues(cursor)
        seed_events(cursor)
        seed_registrations(cursor)

        conn.commit()
        cursor.close()
        conn.close()

        print("\nSeeding completed successfully!")
        print("Admin login:")
        print("Email: admin@gmail.com")
        print("Password: admin123")

    except Exception as e:
        print("Error while seeding database:")
        print(e)


if __name__ == "__main__":
    main()