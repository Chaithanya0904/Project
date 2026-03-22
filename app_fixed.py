# ===================== IMPORTS =====================
import os
import sqlite3
import uuid
import pathlib
import torch
from datetime import datetime
import yaml
import smtplib

from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'wverihdfuvuwi2482'

EMAIL_ADDRESS = "c9074hai@gmail.com"
EMAIL_PASSWORD = "dnhd qnaf dklq jshy"  
ADMIN_EMAIL = "deeplearning251@gmail.com"

# ===================== AI AUTO-PROCESS CONFIG =====================
AUTO_RESOLUTIONS = {
    "broken streetlight": {
        "resolution": "Issue: Broken Streetlight detected. Action: Maintenance team assigned for repair. Timeline: 48 hours.",
        "status": "in_progress"
    },
    "damaged footpath sidewalk": {
        "resolution": "Issue: Damaged Sidewalk detected. Action: Inspection scheduled by Civil Works department.",
        "status": "in_progress"
    },
    "flood": {
        "resolution": "Issue: Flooding detected. Action: Emergency Drainage team dispatched to the coordinates.",
        "status": "in_progress"
    },
    "garbage": {
        "resolution": "Issue: Garbage accumulation detected. Action: Sanitation truck scheduled for immediate pickup.",
        "status": "resolved"
    },
    "open manhole": {
        "resolution": "Issue: Open Manhole detected. Action: URGENT - Safety barrier installation and cover replacement initiated.",
        "status": "in_progress"
    },
    "sewageleak": {
        "resolution": "Issue: Sewage Leak detected. Action: Water and Sewerage Board alerted for leak containment.",
        "status": "in_progress"
    },
    "waterleakage": {
        "resolution": "Issue: Water Leakage detected. Action: Pipeline repair team notified for pressure check and fix.",
        "status": "in_progress"
    }
}

def auto_process_complaint(complaint_id, result_text):
    if not result_text or result_text == "No object detected":
        return
    primary_issue = result_text.split(',')[0].strip().lower()
    if primary_issue in AUTO_RESOLUTIONS:
        config = AUTO_RESOLUTIONS[primary_issue]
        conn = get_db_connection()
        conn.execute(
            "UPDATE complients SET result = ?, status = ? WHERE id = ?",
            (config['resolution'], config['status'], complaint_id)
        )
        conn.commit()
        conn.close()
        print(f"AI Auto-processed: {primary_issue}")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['DATABASE'] = os.path.join(BASE_DIR, 'database.db')
app.config['COMPLAINT_UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads', 'complaints')
app.config['PROFILE_UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'profiles')

os.makedirs(app.config['COMPLAINT_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROFILE_UPLOAD_FOLDER'], exist_ok=True)

def load_class_names():
    if os.path.exists("data.yaml"):
        with open("data.yaml", "r") as f:
            data = yaml.safe_load(f)
        return data["names"]
    return []

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                number TEXT,
                password TEXT NOT NULL,
                image_path TEXT,
                role TEXT DEFAULT 'user'
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS complients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                image_path TEXT,
                result TEXT,
                user_email TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    conn.close()

def allowed_file(filename, filetype):
    if filetype == 'image':
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
    return False

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}

@app.route('/')
def index():
    return render_template('index.html', title="Home")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        number = request.form['number']
        password = request.form['password']
        profile_image = request.files['profile_image']
        role = request.form['role']

        filename = None
        if profile_image and allowed_file(profile_image.filename, 'image'):
            filename = secure_filename(profile_image.filename)
            image_path = os.path.join(app.config['PROFILE_UPLOAD_FOLDER'], filename)
            profile_image.save(image_path)
        
        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO users (name, email, number, password, image_path, role) VALUES (?, ?, ?, ?, ?, ?)',
                (name, email, number, hashed_password, filename, role)
            )
            conn.commit()
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'danger')
        finally:
            conn.close()
    return render_template('register.html', title="Register")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['email'] = user['email']
            session['name'] = user['name']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'index'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html', title="Login")

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/profile')
def profile():
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (session['email'],)).fetchone()
    conn.close()
    return render_template('profile.html', user=user)

# YOLO Integration
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
model.conf = 0.15

def run_yolo_detection(image_path, detection_folder, filename):
    import cv2
    img = cv2.imread(image_path)
    if img is None: return None, "Error"
    results = model(img)
    detected = list(set([model.names[int(cls)] for *box, conf, cls in results.xyxy[0]]))
    result_text = ", ".join(detected) if detected else "No object detected"
    results.render()
    cv2.imwrite(os.path.join(detection_folder, filename), img)
    return f"detections/{filename}", result_text

@app.route('/complaint', methods=['GET', 'POST'])
def complaint():
    if 'email' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        title, desc = request.form.get('title'), request.form.get('description')
        img_file = request.files.get('complaint_image')
        if not title or not desc or not img_file:
            flash('Missing fields', 'danger'); return redirect(request.url)
        
        ext = img_file.filename.rsplit('.', 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        upload_path = os.path.join("static", "uploads", unique_name)
        img_file.save(upload_path)

        det_folder = os.path.join("static", "detections")
        os.makedirs(det_folder, exist_ok=True)
        det_path, res_text = run_yolo_detection(upload_path, det_folder, unique_name)

        conn = get_db_connection()
        cursor = conn.execute("INSERT INTO complients (title, description, image_path, result, user_email) VALUES (?, ?, ?, ?, ?)",
                     (title, desc, det_path, res_text, session['email']))
        conn.commit()
        complaint_id = cursor.lastrowid
        conn.close()

        auto_process_complaint(complaint_id, res_text)
        flash('Complaint filed successfully.', 'success')
        return redirect(url_for('my_complaints'))
    return render_template('complaint.html', title="File Complaint")

@app.route('/my_complaints')
def my_complaints():
    if 'email' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    complaints = conn.execute("SELECT * FROM complients WHERE user_email = ?", (session['email'],)).fetchall()
    conn.close()
    return render_template('my_complaints.html', complaints=complaints)

@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    u_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    c_count = conn.execute("SELECT COUNT(*) FROM complients").fetchone()[0]
    conn.close()
    return render_template('admin_dashboard.html', total_users=u_count, total_complaints=c_count)

@app.route('/admin/complaints')
def admin_complaints():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    complaints = conn.execute("SELECT * FROM complients").fetchall()
    conn.close()
    return render_template('admin_complaints.html', complaints=complaints)

@app.route('/admin/complaint/edit/<int:complaint_id>', methods=['GET', 'POST'])
def admin_complaint_edit(complaint_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    complaint = conn.execute("SELECT * FROM complients WHERE id = ?", (complaint_id,)).fetchone()
    if request.method == 'POST':
        conn.execute("UPDATE complients SET result = ?, status = ? WHERE id = ?", (request.form['result'], request.form['status'], complaint_id))
        conn.commit(); conn.close()
        return redirect(url_for('admin_complaints'))
    conn.close()
    return render_template('admin_complaint_edit.html', complaint=complaint, auto_resolutions=AUTO_RESOLUTIONS)

@app.route('/admin/complaint/auto-process/<int:complaint_id>', methods=['POST'])
def admin_auto_process(complaint_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    complaint = conn.execute("SELECT * FROM complients WHERE id = ?", (complaint_id,)).fetchone()
    conn.close()
    auto_process_complaint(complaint_id, complaint['result'])
    return redirect(url_for('admin_complaints'))

@app.template_filter('time_ago')
def time_ago(value):
    if not value: return ''
    if isinstance(value, str):
        try: value = datetime.fromisoformat(value)
        except: return value
    diff = datetime.now() - value
    sec = diff.total_seconds()
    if sec < 60: return "just now"
    if sec < 3600: return f"{int(sec//60)}m ago"
    if sec < 86400: return f"{int(sec//3600)}h ago"
    return value.strftime("%b %d")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
