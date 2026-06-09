# events_susl_hermes/app.py
"""Events.SUSL - QR-Based University Event Registration & Attendance System."""

import os
import bcrypt
import qrcode
from datetime import datetime, date, time as dt_time
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_from_directory)
from flask_mysqldb import MySQL
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

mysql = MySQL(app)

# ── Custom Jinja filters for pagination ──
def _parse_args(args):
    """Accept either an ImmutableMultiDict or a query string from chained filters."""
    from urllib.parse import parse_qs
    if hasattr(args, 'items'):
        return dict(args)
    if isinstance(args, str):
        result = {}
        for k, v in parse_qs(args).items():
            result[k] = v[0] if v else ''
        return result
    return {}

@app.template_filter('replace_page')
def replace_page(args, page):
    """Replace the 'page' query param, returning a query string."""
    d = _parse_args(args)
    d['page'] = str(page)
    return '&'.join(f'{k}={v}' for k, v in d.items())

@app.template_filter('replace_per_page')
def replace_per_page(args, per_page):
    """Replace the 'per_page' query param."""
    d = _parse_args(args)
    d['per_page'] = str(per_page)
    d['page'] = '1'
    return '&'.join(f'{k}={v}' for k, v in d.items())

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(Config.QR_FOLDER, exist_ok=True)


# ==================== HELPERS ====================

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
EVENT_IMAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'events')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    return mysql.connection

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def update_event_status(event_id):
    """Set event status based on active registrations vs capacity."""
    cur = get_db().cursor()
    cur.execute("SELECT capacity FROM events WHERE id=%s", (event_id,))
    row = cur.fetchone()
    if not row:
        return
    capacity = row['capacity']
    cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE event_id=%s AND status='Active'",
                (event_id,))
    booked = cur.fetchone()['cnt']
    new_status = 'Full' if booked >= capacity else 'Available'
    cur.execute("UPDATE events SET status=%s WHERE id=%s", (new_status, event_id))
    get_db().commit()
    cur.close()

def renumber_registrations(event_id):
    """Renumber active registrations for an event to be continuous 1,2,3..."""
    cur = get_db().cursor()
    cur.execute("SELECT id FROM registrations WHERE event_id=%s AND status='Active' ORDER BY id",
                (event_id,))
    rows = cur.fetchall()
    for idx, row in enumerate(rows, start=1):
        cur.execute("UPDATE registrations SET registration_number=%s WHERE id=%s",
                    (idx, row['id']))
    get_db().commit()
    cur.close()

def registration_is_open(event):
    """Check if registration is open for an event."""
    if not event.get('registration_open', 1):
        return False, 'Registration is not open yet.'
    if event.get('registration_close_date') and event.get('registration_close_time'):
        close_dt = datetime.combine(event['registration_close_date'], event['registration_close_time'])
        if datetime.now() > close_dt:
            return False, 'Registration is closed.'
    return True, ''

ACTIVE_FILTER = "AND status='Active'"


# ==================== PUBLIC ROUTES ====================

@app.route('/')
def index():
    cur = get_db().cursor()
    # All events for stats
    cur.execute("SELECT COUNT(*) AS cnt FROM events")
    total_events = cur.fetchone()['cnt']
    cur.execute("SELECT COALESCE(SUM(capacity),0) AS cnt FROM events")
    total_capacity = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE status='Active'")
    total_regs = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM attendance")
    total_attendance = cur.fetchone()['cnt']

    # Featured: 3 nearest upcoming events (today or later)
    cur.execute("""
    SELECT e.*, c.name AS category_name, v.name AS venue_name,
           (SELECT COUNT(*) FROM registrations WHERE event_id=e.id AND status='Active') AS booked_count
    FROM events e
    LEFT JOIN categories c ON e.category_id=c.id
    LEFT JOIN venues v ON e.venue_id=v.id
    WHERE e.event_date >= CURDATE()
    ORDER BY e.event_date ASC, e.event_time ASC
    LIMIT 3
    """)
    featured_events = cur.fetchall()

    # Recent feedback for home page
    cur.execute("""
    SELECT f.*, e.title AS event_title, r.full_name
    FROM feedback f
    JOIN events e ON f.event_id=e.id
    LEFT JOIN registrations r ON f.registration_id=r.id
    WHERE f.is_deleted=0
    ORDER BY f.submitted_at DESC
    LIMIT 6
    """)
    recent_feedback = cur.fetchall()

    # Past events count for home page
    cur.execute("SELECT COUNT(*) AS cnt FROM events WHERE event_date < CURDATE()")
    past_count = cur.fetchone()['cnt']

    cur.close()
    return render_template('index.html', featured_events=featured_events,
                           total_events=total_events, total_capacity=total_capacity,
                           total_regs=total_regs, total_attendance=total_attendance,
                           recent_feedback=recent_feedback, past_count=past_count)

@app.route('/events')
def events():
    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    cur = get_db().cursor()

    # Build filtered query
    where = "WHERE 1=1"
    params = []

    if category_filter:
        where += " AND c.name=%s"
        params.append(category_filter)

    if search:
        where += " AND (e.title LIKE %s OR v.name LIKE %s OR v.location LIKE %s)"
        like = f"%{search}%"
        params.extend([like, like, like])

    cur.execute(f"""
    SELECT e.*, c.name AS category_name, v.name AS venue_name, v.location AS venue_location,
           (SELECT COUNT(*) FROM registrations WHERE event_id=e.id AND status='Active') AS booked_count
    FROM events e
    LEFT JOIN categories c ON e.category_id=c.id
    LEFT JOIN venues v ON e.venue_id=v.id
    {where}
    ORDER BY e.event_date ASC, e.event_time ASC
    """, params)
    events = cur.fetchall()

    # Compute registration status for each event
    for event in events:
        event['reg_status'] = _compute_reg_status(event)

    # Fetch all categories for filter pills
    cur.execute("SELECT name FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur.close()

    return render_template('events.html', events=events, categories=categories,
                           category_filter=category_filter, search=search)


def _compute_reg_status(event):
    """Return registration status label key for an event dict."""
    if event.get('status') == 'Full':
        return 'full'
    if not event.get('registration_open', 1):
        return 'not_open'
    if event.get('registration_close_date') and event.get('registration_close_time'):
        close_dt = datetime.combine(event['registration_close_date'], event['registration_close_time'])
        if datetime.now() > close_dt:
            return 'closed'
    return 'open'

@app.route('/event/<int:event_id>')
def event_details(event_id):
    cur = get_db().cursor()
    cur.execute("""
    SELECT e.*, c.name AS category_name, v.name AS venue_name,
           (SELECT COUNT(*) FROM registrations WHERE event_id=e.id AND status='Active') AS booked_count
    FROM events e
    LEFT JOIN categories c ON e.category_id=c.id
    LEFT JOIN venues v ON e.venue_id=v.id
    WHERE e.id=%s
    """, (event_id,))
    event = cur.fetchone()
    cur.close()
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events'))
    return render_template('event_details.html', event=event)

@app.route('/register/<int:event_id>', methods=['GET', 'POST'])
def register(event_id):
    cur = get_db().cursor()
    cur.execute("""
    SELECT e.*, c.name AS category_name
    FROM events e LEFT JOIN categories c ON e.category_id=c.id
    WHERE e.id=%s
    """, (event_id,))
    event = cur.fetchone()
    cur.close()
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events'))

    # Registration access check
    reg_open, reg_msg = registration_is_open(event)
    if not reg_open:
        flash(reg_msg, 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    if event['status'] == 'Full':
        flash('This event is fully booked.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        student_id = request.form.get('student_id', '').strip()
        department = request.form.get('department', '').strip()

        if not all([full_name, email, phone, student_id, department]):
            flash('Please fill in all required fields.', 'warning')
            return render_template('register.html', event=event)

        # Check duplicate (only active registrations)
        cur = get_db().cursor()
        cur.execute("SELECT id FROM registrations WHERE email=%s AND event_id=%s AND status='Active'",
                    (email, event_id))
        if cur.fetchone():
            flash('You have already registered for this event with this email.', 'warning')
            cur.close()
            return render_template('register.html', event=event)

        # Check capacity
        cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE event_id=%s AND status='Active'",
                    (event_id,))
        booked = cur.fetchone()['cnt']
        if booked >= event['capacity']:
            flash('Sorry, this event just became full.', 'danger')
            cur.close()
            return redirect(url_for('event_details', event_id=event_id))

        # Assign registration number
        next_num = booked + 1

        # Generate QR code
        qr_value = f"EVENT-{event_id}-{email}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        qr_filename = f"qr_{event_id}_{email.split('@')[0]}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        qr_path = os.path.join(Config.QR_FOLDER, qr_filename)

        img = qrcode.make(qr_value)
        img.save(qr_path)

        cur.execute("""
        INSERT INTO registrations (event_id, registration_number, full_name, email, phone, student_id, department, qr_code)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (event_id, next_num, full_name, email, phone, student_id, department, qr_filename))
        reg_id = cur.lastrowid
        get_db().commit()
        cur.close()

        update_event_status(event_id)

        return redirect(url_for('confirmation', registration_id=reg_id))

    return render_template('register.html', event=event)

@app.route('/confirmation/<int:registration_id>')
def confirmation(registration_id):
    cur = get_db().cursor()
    cur.execute("""
    SELECT r.*, e.title AS event_title, e.event_date, e.event_time,
           v.name AS venue_name
    FROM registrations r
    JOIN events e ON r.event_id=e.id
    LEFT JOIN venues v ON e.venue_id=v.id
    WHERE r.id=%s
    """, (registration_id,))
    reg = cur.fetchone()
    cur.close()
    if not reg:
        flash('Registration not found.', 'danger')
        return redirect(url_for('events'))
    return render_template('confirmation.html', registration=reg)


# ==================== ADMIN AUTH ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        cur = get_db().cursor()
        cur.execute("SELECT * FROM admins WHERE email=%s", (email,))
        admin = cur.fetchone()
        cur.close()
        if admin and bcrypt.checkpw(password.encode('utf-8'),
                                     admin['password_hash'].encode('utf-8')):
            session['admin_id'] = admin['id']
            session['admin_name'] = admin['name']
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


# ==================== ADMIN DASHBOARD ====================

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    cur = get_db().cursor()

    cur.execute("SELECT COUNT(*) AS cnt FROM events")
    total_events = cur.fetchone()['cnt']

    cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE status='Active'")
    total_regs = cur.fetchone()['cnt']

    cur.execute("SELECT COUNT(*) AS cnt FROM attendance")
    total_attendance = cur.fetchone()['cnt']

    cur.execute("SELECT COALESCE(SUM(capacity),0) AS cnt FROM events")
    total_capacity = cur.fetchone()['cnt']
    available = total_capacity - total_regs
    if available < 0:
        available = 0

    cur.execute("SELECT COUNT(*) AS cnt FROM events WHERE status='Full'")
    full_events = cur.fetchone()['cnt']

    cur.execute("""
    SELECT e.title, COUNT(r.id) AS cnt
    FROM events e LEFT JOIN registrations r ON e.id=r.event_id AND r.status='Active'
    GROUP BY e.id ORDER BY cnt DESC LIMIT 1
    """)
    most_registered = cur.fetchone()

    cur.execute("""
    SELECT e.title, COUNT(r.id) AS cnt
    FROM events e LEFT JOIN registrations r ON e.id=r.event_id AND r.status='Active'
    GROUP BY e.id ORDER BY e.id
    """)
    regs_by_event = cur.fetchall()

    cur.execute("""
    SELECT c.name, COUNT(e.id) AS cnt
    FROM categories c LEFT JOIN events e ON c.id=e.category_id
    GROUP BY c.id
    """)
    events_by_cat = cur.fetchall()

    cur.execute("""
    SELECT e.title,
           COUNT(r.id) AS total_reg,
           SUM(r.attendance_status) AS attended
    FROM events e LEFT JOIN registrations r ON e.id=r.event_id AND r.status='Active'
    GROUP BY e.id
    """)
    attendance_data = cur.fetchall()

    cur.execute("""
    SELECT r.*, e.title AS event_title
    FROM registrations r JOIN events e ON r.event_id=e.id
    WHERE r.status='Active'
    ORDER BY r.registered_at DESC LIMIT 6
    """)
    recent_regs = cur.fetchall()
    cur.close()

    return render_template('admin_dashboard.html',
                           total_events=total_events, total_regs=total_regs,
                           total_attendance=total_attendance, available=available,
                           full_events=full_events, most_registered=most_registered,
                           regs_by_event=regs_by_event, events_by_cat=events_by_cat,
                           attendance_data=attendance_data, recent_regs=recent_regs)


# ==================== EVENT MANAGEMENT ====================

@app.route('/admin/events')
@login_required
def admin_events():
    cur = get_db().cursor()
    cur.execute("""
    SELECT e.*, c.name AS category_name, v.name AS venue_name,
           (SELECT COUNT(*) FROM registrations WHERE event_id=e.id AND status='Active') AS booked_count
    FROM events e
    LEFT JOIN categories c ON e.category_id=c.id
    LEFT JOIN venues v ON e.venue_id=v.id
    ORDER BY e.event_date DESC
    """)
    events = cur.fetchall()
    cur.close()
    return render_template('admin_events.html', events=events)

@app.route('/admin/events/add', methods=['GET', 'POST'])
@login_required
def admin_event_add():
    cur = get_db().cursor()
    cur.execute("SELECT * FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur.execute("SELECT * FROM venues ORDER BY name")
    venues = cur.fetchall()
    cur.close()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id')
        venue_id = request.form.get('venue_id')
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time')
        capacity = request.form.get('capacity', 100)
        reg_open = 1 if request.form.get('registration_open') else 0
        reg_close_date = request.form.get('registration_close_date') or None
        reg_close_time = request.form.get('registration_close_time') or None

        if not all([title, event_date, event_time]):
            flash('Please fill in all required fields.', 'warning')
            return render_template('admin_event_form.html', categories=categories,
                                   venues=venues, event=None)

        image_filename = 'default_event.jpg'
        file = request.files.get('event_image')
        if file and file.filename and allowed_file(file.filename):
            import uuid
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            os.makedirs(EVENT_IMAGE_FOLDER, exist_ok=True)
            file.save(os.path.join(EVENT_IMAGE_FOLDER, image_filename))

        cur = get_db().cursor()
        cur.execute("""
        INSERT INTO events (title, description, category_id, venue_id, event_date, event_time,
                            capacity, image, registration_open, registration_close_date, registration_close_time)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (title, description, category_id, venue_id, event_date, event_time,
              capacity, image_filename, reg_open, reg_close_date, reg_close_time))
        get_db().commit()
        cur.close()
        flash('Event added successfully!', 'success')
        return redirect(url_for('admin_events'))

    return render_template('admin_event_form.html', categories=categories,
                           venues=venues, event=None)

@app.route('/admin/events/edit/<int:event_id>', methods=['GET', 'POST'])
@login_required
def admin_event_edit(event_id):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM events WHERE id=%s", (event_id,))
    event = cur.fetchone()
    cur.execute("SELECT * FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur.execute("SELECT * FROM venues ORDER BY name")
    venues = cur.fetchall()
    cur.close()

    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('admin_events'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id')
        venue_id = request.form.get('venue_id')
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time')
        capacity = request.form.get('capacity', 100)
        reg_open = 1 if request.form.get('registration_open') else 0
        reg_close_date = request.form.get('registration_close_date') or None
        reg_close_time = request.form.get('registration_close_time') or None

        if not all([title, event_date, event_time]):
            flash('Please fill in all required fields.', 'warning')
            return render_template('admin_event_form.html', categories=categories,
                                   venues=venues, event=event)

        image_filename = event['image'] or 'default_event.jpg'
        file = request.files.get('event_image')
        if file and file.filename and allowed_file(file.filename):
            import uuid
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            os.makedirs(EVENT_IMAGE_FOLDER, exist_ok=True)
            file.save(os.path.join(EVENT_IMAGE_FOLDER, image_filename))

        cur = get_db().cursor()
        cur.execute("""
        UPDATE events SET title=%s, description=%s, category_id=%s, venue_id=%s,
        event_date=%s, event_time=%s, capacity=%s, image=%s,
        registration_open=%s, registration_close_date=%s, registration_close_time=%s
        WHERE id=%s
        """, (title, description, category_id, venue_id, event_date, event_time,
              capacity, image_filename, reg_open, reg_close_date, reg_close_time, event_id))
        get_db().commit()
        cur.close()
        update_event_status(event_id)
        flash('Event updated!', 'success')
        return redirect(url_for('admin_events'))

    return render_template('admin_event_form.html', categories=categories,
                           venues=venues, event=event)

@app.route('/admin/events/delete/<int:event_id>')
@login_required
def admin_event_delete(event_id):
    cur = get_db().cursor()
    cur.execute("DELETE FROM events WHERE id=%s", (event_id,))
    get_db().commit()
    cur.close()
    flash('Event deleted.', 'info')
    return redirect(url_for('admin_events'))


# ==================== REGISTRATIONS ====================

@app.route('/admin/registrations')
@login_required
def admin_registrations():
    search = request.args.get('search', '').strip()
    event_filter = request.args.get('event_id', '')
    category_filter = request.args.get('category_id', '')
    status_filter = request.args.get('status', '')
    attendance_filter = request.args.get('attendance', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    if per_page not in (25, 50, 100):
        per_page = 25

    cur = get_db().cursor()

    # Dropdowns
    cur.execute("SELECT id, title FROM events ORDER BY event_date DESC")
    events = cur.fetchall()
    cur.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cur.fetchall()

    # ── Build filtered query ──
    base_from = """
    FROM registrations r
    JOIN events e ON r.event_id=e.id
    LEFT JOIN categories c ON e.category_id=c.id
    """
    where = "WHERE 1=1"
    params = []

    if event_filter:
        where += " AND r.event_id=%s"
        params.append(event_filter)
    if category_filter:
        where += " AND e.category_id=%s"
        params.append(category_filter)
    if search:
        where += " AND (r.full_name LIKE %s OR r.email LIKE %s OR r.student_id LIKE %s)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if status_filter:
        where += " AND r.status=%s"
        params.append(status_filter)
    if attendance_filter == 'checked_in':
        where += " AND r.attendance_status=1"
    elif attendance_filter == 'not_checked_in':
        where += " AND r.attendance_status=0"

    # Count total matching
    cur.execute(f"SELECT COUNT(*) AS cnt {base_from} {where}", params)
    total_count = cur.fetchone()['cnt']
    total_pages = max(1, -(-total_count // per_page))  # ceil division
    offset = (page - 1) * per_page

    # Fetch paginated results — active first, then pending
    query = (
        f"SELECT r.*, e.title AS event_title, e.capacity AS event_capacity, "
        f"c.name AS category_name, c.id AS category_id "
        f"{base_from} {where} "
        f"ORDER BY r.status='Active' DESC, r.registration_number ASC "
        f"LIMIT {per_page} OFFSET {offset}"
    )
    cur.execute(query, params)
    all_regs = cur.fetchall()

    active_regs = [r for r in all_regs if r['status'] == 'Active']
    pending_regs = [r for r in all_regs if r['status'] != 'Active']

    # ── Global summary cards ──
    cur.execute("SELECT COUNT(*) AS cnt FROM registrations")
    total_all = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE status='Active'")
    total_active = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE status='Pending'")
    total_pending = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE attendance_status=1")
    total_attended = cur.fetchone()['cnt']
    cur.execute("SELECT COALESCE(SUM(capacity),0) AS cnt FROM events")
    total_capacity = cur.fetchone()['cnt']
    available = max(0, total_capacity - total_active)

    # ── Category-wise summary ──
    cur.execute("""
    SELECT c.id, c.name,
           COALESCE(SUM(CASE WHEN r.status='Active' THEN 1 ELSE 0 END),0) AS cnt
    FROM categories c
    LEFT JOIN events e ON c.id=e.category_id
    LEFT JOIN registrations r ON e.id=r.event_id
    GROUP BY c.id, c.name
    ORDER BY cnt DESC
    """)
    cat_summary = cur.fetchall()

    # ── Event-wise summary ──
    cur.execute("""
    SELECT e.id, e.title, e.capacity, e.status AS event_status,
           c.name AS category_name,
           COALESCE(SUM(CASE WHEN r.status='Active' THEN 1 ELSE 0 END),0) AS active_count,
           COALESCE(SUM(CASE WHEN r.status='Pending' THEN 1 ELSE 0 END),0) AS pending_count,
           COALESCE(SUM(CASE WHEN r.attendance_status=1 THEN 1 ELSE 0 END),0) AS attended_count,
           COALESCE(SUM(CASE WHEN r.status='Active' THEN 1 ELSE 0 END),0) AS booked_pct
    FROM events e
    LEFT JOIN categories c ON e.category_id=c.id
    LEFT JOIN registrations r ON e.id=r.event_id
    GROUP BY e.id, c.name
    ORDER BY e.event_date DESC
    """)
    event_summary = cur.fetchall()
    cur.close()

    return render_template('admin_registrations.html',
                           active_registrations=active_regs,
                           pending_registrations=pending_regs,
                           events=events, categories=categories,
                           event_filter=event_filter, category_filter=category_filter,
                           status_filter=status_filter, attendance_filter=attendance_filter,
                           search=search, page=page, per_page=per_page,
                           total_pages=total_pages, total_count=total_count,
                           total_all=total_all, total_active=total_active,
                           total_pending=total_pending, total_attended=total_attended,
                           available=available,
                           cat_summary=cat_summary, event_summary=event_summary)


@app.route('/admin/registrations/export')
@login_required
def admin_registrations_export():
    """Export filtered registrations as CSV."""
    import csv, io
    from flask import Response

    search = request.args.get('search', '').strip()
    event_filter = request.args.get('event_id', '')
    category_filter = request.args.get('category_id', '')
    status_filter = request.args.get('status', '')
    attendance_filter = request.args.get('attendance', '')

    cur = get_db().cursor()

    where = "WHERE 1=1"
    params = []

    if event_filter:
        where += " AND r.event_id=%s"
        params.append(event_filter)
    if category_filter:
        where += " AND e.category_id=%s"
        params.append(category_filter)
    if search:
        where += " AND (r.full_name LIKE %s OR r.email LIKE %s OR r.student_id LIKE %s)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if status_filter:
        where += " AND r.status=%s"
        params.append(status_filter)
    if attendance_filter == 'checked_in':
        where += " AND r.attendance_status=1"
    elif attendance_filter == 'not_checked_in':
        where += " AND r.attendance_status=0"

    cur.execute(f"""
    SELECT r.registration_number, e.title AS event_title, c.name AS category_name,
           r.full_name, r.email, r.phone, r.student_id, r.department,
           r.qr_code, r.status, r.registered_at
    FROM registrations r
    JOIN events e ON r.event_id=e.id
    LEFT JOIN categories c ON e.category_id=c.id
    {where}
    ORDER BY r.status='Active' DESC, r.registration_number ASC
    """, params)
    rows = cur.fetchall()
    cur.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Registration No', 'Event', 'Category', 'Name', 'Email',
                     'Phone', 'Student ID', 'Department', 'QR Code', 'Status',
                     'Registered At'])
    for r in rows:
        writer.writerow([
            r.get('registration_number', ''),
            r.get('event_title', ''),
            r.get('category_name', ''),
            r.get('full_name', ''),
            r.get('email', ''),
            r.get('phone', ''),
            r.get('student_id', ''),
            r.get('department', ''),
            r.get('qr_code', ''),
            r.get('status', ''),
            r.get('registered_at', ''),
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=registrations_export.csv'}
    )

@app.route('/admin/registrations/cancel/<int:reg_id>')
@login_required
def admin_cancel_registration(reg_id):
    cur = get_db().cursor()
    cur.execute("SELECT event_id FROM registrations WHERE id=%s", (reg_id,))
    row = cur.fetchone()
    if not row:
        flash('Registration not found.', 'danger')
        cur.close()
        return redirect(url_for('admin_registrations'))

    event_id = row['event_id']
    # Mark as Pending
    cur.execute("UPDATE registrations SET status='Pending', registration_number=0, removed_at=NOW() WHERE id=%s", (reg_id,))
    get_db().commit()
    cur.close()

    # Renumber remaining active registrations
    renumber_registrations(event_id)
    update_event_status(event_id)

    flash('Registration moved to Pending list. Seat freed.', 'success')
    return redirect(url_for('admin_registrations'))


@app.route('/admin/registrations/restore/<int:reg_id>')
@login_required
def admin_restore_registration(reg_id):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM registrations WHERE id=%s", (reg_id,))
    reg = cur.fetchone()
    if not reg:
        flash('Registration not found.', 'danger')
        cur.close()
        return redirect(url_for('admin_registrations'))

    event_id = reg['event_id']

    # Check capacity
    cur.execute("SELECT COUNT(*) AS cnt FROM registrations WHERE event_id=%s AND status='Active'",
                (event_id,))
    booked = cur.fetchone()['cnt']
    cur.execute("SELECT capacity FROM events WHERE id=%s", (event_id,))
    event = cur.fetchone()
    if event and booked >= event['capacity']:
        flash('Cannot add back. Event is already full.', 'danger')
        cur.close()
        return redirect(url_for('admin_registrations'))

    # Assign next registration number
    next_num = booked + 1

    cur.execute("""
    UPDATE registrations SET status='Active', registration_number=%s, restored_at=NOW()
    WHERE id=%s
    """, (next_num, reg_id))
    get_db().commit()
    cur.close()

    update_event_status(event_id)

    flash(f'Registration restored as seat #{next_num}.', 'success')
    return redirect(url_for('admin_registrations'))


# ==================== ATTENDANCE ====================

@app.route('/admin/attendance')
@login_required
def admin_attendance():
    cur = get_db().cursor()
    cur.execute("""
    SELECT a.*, e.title AS event_title, r.full_name, r.email, r.qr_code, r.registration_number, r.status AS reg_status
    FROM attendance a
    JOIN registrations r ON a.registration_id=r.id
    JOIN events e ON a.event_id=e.id
    ORDER BY a.check_in_time DESC
    """)
    records = cur.fetchall()
    cur.close()
    return render_template('admin_attendance.html', records=records)

@app.route('/admin/scan-attendance', methods=['GET', 'POST'])
@login_required
def scan_attendance():
    if request.method == 'POST':
        qr_value = request.form.get('qr_value', '').strip()
        if not qr_value:
            flash('Please enter a QR code or registration ID.', 'warning')
            return render_template('scan_attendance.html')

        cur = get_db().cursor()

        reg = None
        if qr_value.isdigit():
            cur.execute("SELECT * FROM registrations WHERE id=%s", (qr_value,))
            reg = cur.fetchone()

        if not reg:
            cur.execute("SELECT * FROM registrations WHERE qr_code=%s", (qr_value,))
            reg = cur.fetchone()

        if not reg:
            flash('Invalid QR code. Registration not found.', 'danger')
            cur.close()
            return render_template('scan_attendance.html')

        if reg['status'] != 'Active':
            flash('This registration is not active.', 'danger')
            cur.close()
            return render_template('scan_attendance.html')

        if reg['attendance_status'] == 1:
            flash(f'{reg["full_name"]} has already been checked in.', 'warning')
            cur.close()
            return render_template('scan_attendance.html')

        cur.execute("UPDATE registrations SET attendance_status=1, check_in_time=NOW() WHERE id=%s",
                    (reg['id'],))
        cur.execute("INSERT INTO attendance (registration_id, event_id) VALUES (%s, %s)",
                    (reg['id'], reg['event_id']))
        get_db().commit()

        cur.execute("SELECT title FROM events WHERE id=%s", (reg['event_id'],))
        event_title = cur.fetchone()['title']
        cur.close()

        flash(f'Check-in successful! #{reg["registration_number"]} {reg["full_name"]} — {event_title}', 'success')
        return render_template('scan_attendance.html')

    return render_template('scan_attendance.html')


# ==================== FEEDBACK ====================

@app.route('/feedback/submit', methods=['POST'])
def submit_feedback():
    event_id = request.form.get('event_id', type=int)
    registration_code = request.form.get('registration_code', '').strip()
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not event_id or not rating:
        flash('Event and rating are required.', 'warning')
        return redirect(request.referrer or url_for('events'))

    if rating < 1 or rating > 5:
        flash('Rating must be between 1 and 5.', 'warning')
        return redirect(request.referrer or url_for('events'))

    cur = get_db().cursor()

    # Look up registration if code provided
    reg_id = None
    reg_email = None
    if registration_code:
        cur.execute("SELECT id, email FROM registrations WHERE qr_code=%s AND event_id=%s AND status='Active'",
                    (registration_code, event_id))
        reg = cur.fetchone()
        if reg:
            reg_id = reg['id']
            reg_email = reg['email']

    # Check duplicate: one feedback per registration per event
    if reg_id:
        cur.execute("SELECT id FROM feedback WHERE registration_id=%s AND is_deleted=0", (reg_id,))
        if cur.fetchone():
            flash('You have already submitted feedback for this event.', 'warning')
            cur.close()
            return redirect(request.referrer or url_for('events'))

    cur.execute("""
    INSERT INTO feedback (event_id, registration_id, rating, comment)
    VALUES (%s, %s, %s, %s)
    """, (event_id, reg_id, rating, comment))
    get_db().commit()
    cur.close()

    flash('Thank you for your feedback.', 'success')
    return redirect(request.referrer or url_for('events'))


# ==================== PAST EVENTS ====================

@app.route('/past-events')
def past_events():
    cur = get_db().cursor()
    cur.execute("""
    SELECT e.*, c.name AS category_name, v.name AS venue_name,
           (SELECT COUNT(*) FROM registrations WHERE event_id=e.id AND status='Active') AS booked_count,
           (SELECT ROUND(AVG(rating),1) FROM feedback WHERE event_id=e.id AND is_deleted=0) AS avg_rating,
           (SELECT COUNT(*) FROM feedback WHERE event_id=e.id AND is_deleted=0) AS feedback_count
    FROM events e
    LEFT JOIN categories c ON e.category_id=c.id
    LEFT JOIN venues v ON e.venue_id=v.id
    WHERE e.event_date < CURDATE()
    ORDER BY e.event_date DESC
    """)
    events = cur.fetchall()
    cur.close()
    return render_template('past_events.html', events=events)


@app.route('/past-event/<int:event_id>')
def past_event_details(event_id):
    cur = get_db().cursor()
    cur.execute("""
    SELECT e.*, c.name AS category_name, v.name AS venue_name,
           (SELECT COUNT(*) FROM registrations WHERE event_id=e.id AND status='Active') AS booked_count,
           (SELECT COUNT(*) FROM attendance WHERE event_id=e.id) AS attended_count
    FROM events e
    LEFT JOIN categories c ON e.category_id=c.id
    LEFT JOIN venues v ON e.venue_id=v.id
    WHERE e.id=%s
    """, (event_id,))
    event = cur.fetchone()

    if not event:
        cur.close()
        flash('Event not found.', 'danger')
        return redirect(url_for('past_events'))

    # Feedback stats
    cur.execute("""
    SELECT ROUND(AVG(rating),1) AS avg_rating, COUNT(*) AS cnt
    FROM feedback WHERE event_id=%s AND is_deleted=0
    """, (event_id,))
    fb_stats = cur.fetchone()

    # Rating distribution
    cur.execute("""
    SELECT rating, COUNT(*) AS cnt FROM feedback
    WHERE event_id=%s AND is_deleted=0
    GROUP BY rating ORDER BY rating DESC
    """, (event_id,))
    rating_dist = cur.fetchall()
    dist = {1:0, 2:0, 3:0, 4:0, 5:0}
    for r in rating_dist:
        dist[r['rating']] = r['cnt']
    total_fb = sum(dist.values())

    # Feedback comments
    cur.execute("""
    SELECT f.*, r.full_name, r.email
    FROM feedback f
    LEFT JOIN registrations r ON f.registration_id=r.id
    WHERE f.event_id=%s AND f.is_deleted=0
    ORDER BY f.submitted_at DESC
    """, (event_id,))
    feedbacks = cur.fetchall()

    # Media gallery
    cur.execute("SELECT * FROM event_media WHERE event_id=%s ORDER BY uploaded_at DESC", (event_id,))
    media = cur.fetchall()

    cur.close()
    return render_template('past_event_details.html', event=event,
                           fb_stats=fb_stats, dist=dist, total_fb=total_fb,
                           feedbacks=feedbacks, media=media)


# ==================== ADMIN FEEDBACK ====================

@app.route('/admin/feedback')
@login_required
def admin_feedback():
    event_filter = request.args.get('event_id', '')
    cur = get_db().cursor()

    where = "WHERE 1=1"
    params = []
    if event_filter:
        where += " AND f.event_id=%s"
        params.append(event_filter)

    cur.execute(f"""
    SELECT f.*, e.title AS event_title, r.full_name, r.email
    FROM feedback f
    JOIN events e ON f.event_id=e.id
    LEFT JOIN registrations r ON f.registration_id=r.id
    {where}
    ORDER BY f.submitted_at DESC
    """, params)
    feedbacks = cur.fetchall()

    cur.execute("SELECT id, title FROM events ORDER BY event_date DESC")
    events = cur.fetchall()
    cur.close()
    return render_template('admin_feedback.html', feedbacks=feedbacks,
                           events=events, event_filter=event_filter)


@app.route('/admin/feedback/delete/<int:fb_id>')
@login_required
def admin_delete_feedback(fb_id):
    cur = get_db().cursor()
    # Soft delete
    cur.execute("UPDATE feedback SET is_deleted=1 WHERE id=%s", (fb_id,))
    get_db().commit()
    cur.close()
    flash('Feedback removed.', 'info')
    return redirect(url_for('admin_feedback'))


# ==================== ADMIN MEDIA ====================

@app.route('/admin/media')
@login_required
def admin_media():
    event_filter = request.args.get('event_id', '')
    cur = get_db().cursor()

    where = "WHERE 1=1"
    params = []
    if event_filter:
        where += " AND m.event_id=%s"
        params.append(event_filter)

    cur.execute(f"""
    SELECT m.*, e.title AS event_title
    FROM event_media m
    JOIN events e ON m.event_id=e.id
    {where}
    ORDER BY m.uploaded_at DESC
    """, params)
    media = cur.fetchall()

    cur.execute("SELECT id, title FROM events ORDER BY event_date DESC")
    events = cur.fetchall()
    cur.close()
    return render_template('admin_media.html', media=media,
                           events=events, event_filter=event_filter)


@app.route('/admin/media/upload', methods=['POST'])
@login_required
def admin_media_upload():
    event_id = request.form.get('event_id', type=int)
    caption = request.form.get('caption', '').strip()
    media_type = request.form.get('media_type', 'photo')

    if not event_id:
        flash('Please select an event.', 'warning')
        return redirect(url_for('admin_media'))

    filename = None
    url = None

    if media_type == 'video':
        url = request.form.get('video_url', '').strip()
        if not url:
            flash('Please provide a video URL.', 'warning')
            return redirect(url_for('admin_media'))

    else:
        file = request.files.get('media_file')
        if not file or not file.filename:
            flash('Please select a file.', 'warning')
            return redirect(url_for('admin_media'))

        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4'):
            flash('Unsupported file type.', 'warning')
            return redirect(url_for('admin_media'))

        import uuid
        filename = f"media_{uuid.uuid4().hex}.{ext}"
        media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'media')
        os.makedirs(media_dir, exist_ok=True)
        file.save(os.path.join(media_dir, filename))

        if ext == 'mp4':
            media_type = 'video'

    cur = get_db().cursor()
    cur.execute("""
    INSERT INTO event_media (event_id, media_type, filename, url, caption)
    VALUES (%s, %s, %s, %s, %s)
    """, (event_id, media_type, filename, url, caption))
    get_db().commit()
    cur.close()

    flash('Media uploaded!', 'success')
    return redirect(url_for('admin_media'))


@app.route('/admin/media/delete/<int:media_id>')
@login_required
def admin_delete_media(media_id):
    cur = get_db().cursor()
    cur.execute("SELECT filename FROM event_media WHERE id=%s", (media_id,))
    row = cur.fetchone()
    if row and row['filename']:
        media_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'static', 'uploads', 'media', row['filename'])
        if os.path.exists(media_path):
            os.remove(media_path)
    cur.execute("DELETE FROM event_media WHERE id=%s", (media_id,))
    get_db().commit()
    cur.close()
    flash('Media deleted.', 'info')
    return redirect(url_for('admin_media'))


# ==================== STATIC FILES ====================

@app.route('/static/qrcodes/<filename>')
def qrcode_file(filename):
    return send_from_directory(Config.QR_FOLDER, filename)


# ==================== RUN ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
