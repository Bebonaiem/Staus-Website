import os
import sqlite3
from flask_login import UserMixin
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

load_dotenv()
bcrypt = Bcrypt()

db_path = os.path.join(os.path.dirname(__file__), '..', 'statuspage.db')

def get_db_connection():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    schema = """
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL, status TEXT DEFAULT 'Checking...', last_checked DATETIME, response_time INTEGER, icon TEXT DEFAULT 'fa-solid fa-globe');
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS incidents (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, status TEXT NOT NULL, severity TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS incident_updates (id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id INTEGER NOT NULL, update_text TEXT NOT NULL, status TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (incident_id) REFERENCES incidents (id) ON DELETE CASCADE);
    
    /* MODIFIED: Removed 'status' column as it can be derived */
    CREATE TABLE IF NOT EXISTS scheduled_maintenances (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, start_time DATETIME NOT NULL, end_time DATETIME NOT NULL);
    
    /* NEW: Table to link maintenances with services */
    CREATE TABLE IF NOT EXISTS maintenance_services (
        maintenance_id INTEGER NOT NULL,
        service_id INTEGER NOT NULL,
        FOREIGN KEY (maintenance_id) REFERENCES scheduled_maintenances (id) ON DELETE CASCADE,
        FOREIGN KEY (service_id) REFERENCES services (id) ON DELETE CASCADE,
        PRIMARY KEY (maintenance_id, service_id)
    );

    CREATE TABLE IF NOT EXISTS status_history (id INTEGER PRIMARY KEY AUTOINCREMENT, service_id INTEGER NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL, response_time INTEGER, FOREIGN KEY (service_id) REFERENCES services (id) ON DELETE CASCADE);
    """
    cursor.executescript(schema)
    
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_pass = os.environ.get('ADMIN_PASSWORD')
    user = cursor.execute('SELECT * FROM users WHERE email = ?', (admin_email,)).fetchone()
    if not user and admin_email and admin_pass:
        hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
        cursor.execute('INSERT INTO users (email, password) VALUES (?, ?)', (admin_email, hashed_password))
        print("Default admin user created.")

    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('slack_webhook_url', ?)", (os.environ.get('SLACK_WEBHOOK_URL', ''),))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('page_title', 'System Status')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('check_interval_seconds', '60')")

    conn.commit()
    conn.close()

def get_user_by_id(user_id):
    conn = get_db_connection()
    user_row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return User(id=user_row['id'], email=user_row['email']) if user_row else None

def get_user_row_by_email(email):
    conn = get_db_connection()
    user_row = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    return user_row