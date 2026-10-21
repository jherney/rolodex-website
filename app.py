from flask import Flask, jsonify, request, send_from_directory, send_file, redirect, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import secrets
import io
import csv
import re
import urllib.parse
import urllib.request
from datetime import datetime
import psycopg2
import psycopg2.extras

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTACTS_PATH = os.path.join(BASE_DIR, 'contacts.json')
# The vintage desk-rolodex frontend, served at /vintage/ against the same API
VINTAGE_DIR = os.path.abspath(os.environ.get(
    'ROLODEX_VINTAGE_DIR', os.path.join(BASE_DIR, 'vintage-rolodex')))

app = Flask(__name__)

# ── Production configuration ───────────────────────────────────────────
# All configurable via environment variables for 12-factor compliance
PORT = int(os.environ.get('ROLODEX_PORT', '5000'))
# Loopback by default: the API has no authentication, so don't expose it to the network
HOST = os.environ.get('ROLODEX_HOST', '127.0.0.1')
DEBUG = os.environ.get('ROLODEX_DEBUG', '0').lower() in ('1', 'true', 'yes')
# Signs the session cookie. Required on Vercel (serverless instances must share it);
# locally a random key is generated, so sessions end when the server restarts.
SECRET_KEY = os.environ.get('ROLODEX_SECRET_KEY', '')
if not SECRET_KEY:
    if os.environ.get('VERCEL') or os.environ.get('ROLODEX_ENV') == 'production':
        raise RuntimeError('ROLODEX_SECRET_KEY must be set in production')
    SECRET_KEY = secrets.token_hex(32)
# Empty = same-origin only (both bundled frontends are served by this app)
CORS_ORIGIN = os.environ.get('ROLODEX_CORS_ORIGIN', '')
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('VERCEL') or os.environ.get('ROLODEX_SECURE_COOKIES'))
app.config['PERMANENT_SESSION_LIFETIME'] = 30 * 24 * 3600

# PostgreSQL configuration
DB_CONFIG = {
    'host': os.environ.get('ROLODEX_DB_HOST', 'localhost'),
    'port': int(os.environ.get('ROLODEX_DB_PORT', '5432')),
    'dbname': os.environ.get('ROLODEX_DB_NAME', 'rolodex'),
    'user': os.environ.get('ROLODEX_DB_USER', 'rolodex'),
    'password': os.environ.get('ROLODEX_DB_PASSWORD', 'rolodex123'),
}

# Fireworks AI config — recommend setting via env in production
# Fallback to file if env var is missing or appears truncated (contains '...')
FIREWORKS_API_KEY = os.environ.get('FIREWORKS_API_KEY', '')
if not FIREWORKS_API_KEY or '...' in FIREWORKS_API_KEY:
    try:
        with open('/tmp/fireworks_key.txt', 'r') as f:
            FIREWORKS_API_KEY = f.read().strip()
    except Exception:
        pass

# Use a model that follows JSON-only instructions better
FIREWORKS_MODEL = os.environ.get('FIREWORKS_MODEL', 'accounts/fireworks/models/deepseek-v4-flash')

FIREWORKS_API = os.environ.get('FIREWORKS_API_URL', 'https://api.fireworks.ai/inference/v1')

def _set_cors_headers(response):
    if CORS_ORIGIN:
        response.headers['Access-Control-Allow-Origin'] = CORS_ORIGIN
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

@app.after_request
def add_cors_headers(response):
    return _set_cors_headers(response)

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return _set_cors_headers(app.make_response(''))

# ── Database helpers ───────────────────────────────────────────────────

# Hosted Postgres integrations on Vercel set POSTGRES_URL (Supabase) or DATABASE_URL (Neon)
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL', '')

def _dsn_without_supabase_params(url):
    # Supabase's pooled URLs carry a `supa` routing parameter that libpq rejects
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != 'supa']
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))

def get_db_conn():
    if DATABASE_URL:
        return psycopg2.connect(_dsn_without_supabase_params(DATABASE_URL))
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    """Create contacts table if it doesn't exist."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # Every gunicorn worker runs this at import; on a fresh database concurrent
            # CREATE TABLE IF NOT EXISTS calls collide, so serialize them.
            cur.execute("SELECT pg_advisory_xact_lock(727274)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    phone VARCHAR(100),
                    email VARCHAR(255),
                    address TEXT,
                    tags JSONB DEFAULT '[]',
                    notes TEXT,
                    avatar TEXT,
                    birthday VARCHAR(50),
                    social JSONB DEFAULT '{}',
                    linked_contacts JSONB DEFAULT '[]',
                    starred BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
            # Added for the vintage rolodex frontend; optional for other clients
            cur.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS company VARCHAR(255) DEFAULT ''")
            cur.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS title VARCHAR(255) DEFAULT ''")
            # Accounts. Each contact belongs to one user; contacts saved before accounts existed
            # have no user_id and are not visible to anyone.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR(255) PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            cur.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)")
            cur.execute("CREATE INDEX IF NOT EXISTS contacts_user_idx ON contacts (user_id)")
            # Per-contact reminders and activity log. contact_id has no foreign key on purpose:
            # /save_contacts truncates contacts, and a cascade would wipe these rows with it.
            # Routes that delete or merge contacts remove or move these rows explicitly.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id VARCHAR(255) PRIMARY KEY,
                    contact_id VARCHAR(255) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT DEFAULT '',
                    due_date VARCHAR(50) NOT NULL,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS reminders_contact_idx ON reminders (contact_id)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    id VARCHAR(255) PRIMARY KEY,
                    contact_id VARCHAR(255) NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    notes TEXT DEFAULT '',
                    timestamp VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS activities_contact_idx ON activities (contact_id)")
        conn.commit()
    finally:
        conn.close()

# Initialize DB on first import (safe to call multiple times)
init_db()

def _new_id():
    return datetime.now().strftime('%Y%m%d%H%M%S%f') + os.urandom(4).hex()

def _text(data, key):
    """A stripped string field from request JSON; missing, null or non-string values become ''."""
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ''

def current_user_id():
    return session.get('uid')

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            return jsonify({'error': 'login required'}), 401
        return view(*args, **kwargs)
    return wrapper

def _row_to_dict(row):
    """Convert a RealDictRow to a plain dict with camelCase keys for createdAt/updatedAt."""
    d = dict(row)
    # Rename created_at / updated_at to createdAt / updatedAt for API compat
    d['createdAt'] = d.pop('created_at', None)
    d['updatedAt'] = d.pop('updated_at', None)
    # Ensure JSON fields are lists/dicts
    if isinstance(d.get('tags'), str):
        d['tags'] = json.loads(d['tags']) if d['tags'] else []
    if isinstance(d.get('social'), str):
        d['social'] = json.loads(d['social']) if d['social'] else {}
    if isinstance(d.get('linked_contacts'), str):
        d['linked_contacts'] = json.loads(d['linked_contacts']) if d['linked_contacts'] else []
    return d

def load_contacts(uid):
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM contacts WHERE user_id = %s ORDER BY created_at", (uid,))
            rows = cur.fetchall()
            return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()

def save_contacts(contacts, uid):
    """Legacy atomic write: replace this user's contacts with the given list (used by /save_contacts and merge)."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contacts WHERE user_id = %s", (uid,))
            for c in contacts:
                cur.execute(
                    """
                    INSERT INTO contacts
                    (id, name, phone, email, address, tags, notes, avatar, birthday,
                     social, linked_contacts, starred, created_at, updated_at, company, title, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        c.get('id'),
                        c.get('name', ''),
                        c.get('phone', ''),
                        c.get('email', ''),
                        c.get('address', ''),
                        json.dumps(c.get('tags', [])),
                        c.get('notes', ''),
                        c.get('avatar', ''),
                        c.get('birthday', ''),
                        json.dumps(c.get('social', {})),
                        json.dumps(c.get('linked_contacts', [])),
                        bool(c.get('starred', False)),
                        c.get('createdAt', datetime.now().isoformat()),
                        c.get('updatedAt', datetime.now().isoformat()),
                        c.get('company', ''),
                        c.get('title', ''),
                        uid,
                    )
                )
        conn.commit()
    finally:
        conn.close()

# ── Health check (for k8s/Docker compose probes) ───────────────────────
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for container orchestration."""
    db_ok = False
    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
            db_ok = True
        conn.close()
    except Exception:
        pass

    return jsonify({
        'status': 'healthy' if db_ok else 'degraded',
        'db_connected': db_ok,
        'fireworks_configured': bool(FIREWORKS_API_KEY),
        'version': '2.1.0'
    })

@app.route('/ready', methods=['GET'])
def readiness():
    """Readiness probe — verifies DB is reachable and contacts table exists."""
    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
        conn.close()
        return jsonify({'status': 'ready'})
    except Exception as e:
        return jsonify({'status': 'not_ready', 'error': str(e)}), 503

# ── Static file serving ────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    # The vintage desk rolodex is the default page; the original UI is no longer served at /
    return send_from_directory(VINTAGE_DIR, 'index.html')

@app.route('/app.js', methods=['GET'])
def app_js():
    return send_from_directory(BASE_DIR, 'app.js')

@app.route('/styles.css', methods=['GET'])
def styles_css():
    return send_from_directory(BASE_DIR, 'styles.css')

@app.route('/manifest.json', methods=['GET'])
def manifest():
    return send_from_directory(BASE_DIR, 'manifest.json')

@app.route('/sw.js', methods=['GET'])
def sw():
    return send_from_directory(BASE_DIR, 'sw.js')

@app.route('/vintage', methods=['GET'])
def vintage_redirect():
    return redirect('/vintage/', code=301)

@app.route('/vintage/', defaults={'path': 'index.html'}, methods=['GET'])
@app.route('/vintage/<path:path>', methods=['GET'])
def vintage(path):
    return send_from_directory(VINTAGE_DIR, path)

# ── Legacy endpoints (backward compat) ─────────────────────────────────

# ── Accounts ────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

def _password_from(data):
    return data.get('password') if isinstance(data.get('password'), str) else ''

@app.route('/api/v1/auth/signup', methods=['POST'])
def api_signup():
    """Create an account and sign in. Anyone can sign up; each account sees only its own contacts."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'expected a JSON object'}), 400
    email = _text(data, 'email').lower()
    password = _password_from(data)
    if not _EMAIL_RE.match(email):
        return jsonify({'error': 'enter a valid email address'}), 400
    if len(password) < 10:
        return jsonify({'error': 'password must be at least 10 characters'}), 400

    uid = _new_id()
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (%s, %s, %s, %s)",
                (uid, email, generate_password_hash(password), datetime.now()))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'error': 'an account with this email already exists'}), 409
    finally:
        conn.close()

    session.clear()
    session.permanent = True
    session['uid'] = uid
    return jsonify({'email': email}), 201

@app.route('/api/v1/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'expected a JSON object'}), 400
    email = _text(data, 'email').lower()
    password = _password_from(data)
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, email, password_hash FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not check_password_hash(row['password_hash'], password):
        return jsonify({'error': 'email or password is incorrect'}), 401

    session.clear()
    session.permanent = True
    session['uid'] = row['id']
    return jsonify({'email': row['email']})

@app.route('/api/v1/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'status': 'ok'})

@app.route('/api/v1/auth/me', methods=['GET'])
def api_me():
    uid = current_user_id()
    if not uid:
        return jsonify({'error': 'login required'}), 401
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM users WHERE id = %s", (uid,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        session.clear()
        return jsonify({'error': 'login required'}), 401
    return jsonify({'email': row[0]})

@app.route('/get_contacts', methods=['GET'])
@login_required
def get_contacts():
    return jsonify(load_contacts(current_user_id()))

@app.route('/save_contacts', methods=['POST'])
@login_required
def save_contacts_legacy():
    data = request.get_json(silent=True)
    if not isinstance(data, list):
        return jsonify({'error': 'expected a JSON list of contacts'}), 400
    save_contacts(data, current_user_id())
    return jsonify({'status': 'ok', 'count': len(data)})

# ── API v1 endpoints ───────────────────────────────────────────────────

@app.route('/api/v1/contacts', methods=['GET'])
@login_required
def api_get_contacts():
    """Get the signed-in user's contacts. Supports ?search= and ?tag= filtering."""
    uid = current_user_id()
    search = request.args.get('search', '').strip().lower()
    tag_filter = request.args.get('tag', '').strip().lower()

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if tag_filter:
                # Tags keep their original case; match case-insensitively
                cur.execute(
                    """
                    SELECT * FROM contacts
                    WHERE user_id = %s
                      AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(tags) t WHERE LOWER(t) = %s)
                    ORDER BY created_at
                    """,
                    (uid, tag_filter)
                )
            elif search:
                # Every word must appear in some field (name, phone, email, address, notes, tags, company, title)
                terms = search.split()
                searchable = "LOWER(CONCAT_WS(' ', name, phone, email, address, notes, tags::text, company, title))"
                cur.execute(
                    f"SELECT * FROM contacts WHERE user_id = %s AND {' AND '.join([searchable + ' LIKE %s'] * len(terms))} ORDER BY created_at",
                    [uid] + [f'%{term}%' for term in terms]
                )
            else:
                cur.execute("SELECT * FROM contacts WHERE user_id = %s ORDER BY created_at", (uid,))
            rows = cur.fetchall()
    finally:
        conn.close()

    return jsonify([_row_to_dict(r) for r in rows])

@app.route('/api/v1/contacts', methods=['POST'])
@login_required
def api_add_contact():
    """Add a new contact."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not _text(data, 'name'):
        return jsonify({'error': 'name is required'}), 400

    contact = {
        'id': _text(data, 'id') or _new_id(),
        'name': _text(data, 'name'),
        'phone': _text(data, 'phone'),
        'email': _text(data, 'email'),
        'address': _text(data, 'address'),
        'tags': data.get('tags') or [],
        'notes': _text(data, 'notes'),
        'avatar': _text(data, 'avatar'),
        'birthday': _text(data, 'birthday'),
        'social': data.get('social') or {},
        'linked_contacts': data.get('linked_contacts') or [],
        'starred': bool(data.get('starred', False)),
        'company': _text(data, 'company'),
        'title': _text(data, 'title'),
        'createdAt': datetime.now().isoformat(),
        'updatedAt': datetime.now().isoformat()
    }

    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contacts
                (id, name, phone, email, address, tags, notes, avatar, birthday,
                 social, linked_contacts, starred, created_at, updated_at, company, title, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    contact['id'],
                    contact['name'],
                    contact['phone'],
                    contact['email'],
                    contact['address'],
                    json.dumps(contact['tags']),
                    contact['notes'],
                    contact['avatar'],
                    contact['birthday'],
                    json.dumps(contact['social']),
                    json.dumps(contact['linked_contacts']),
                    bool(contact['starred']),
                    contact['createdAt'],
                    contact['updatedAt'],
                    contact['company'],
                    contact['title'],
                    current_user_id(),
                )
            )
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'error': 'contact with this id already exists'}), 409
    finally:
        conn.close()

    return jsonify({'status': 'ok', 'contact': contact}), 201

@app.route('/api/v1/contacts/<contact_id>', methods=['PUT'])
@login_required
def api_update_contact(contact_id):
    """Update one of the signed-in user's contacts."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({'error': 'no data'}), 400
    if 'name' in data and not _text(data, 'name'):
        return jsonify({'error': 'name cannot be empty'}), 400

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Build dynamic update
            fields = []
            params = []
            for field in ['name','phone','email','address','tags','notes',
                          'avatar','birthday','social','linked_contacts','starred',
                          'company','title']:
                if field in data:
                    fields.append(f"{field} = %s")
                    if field in ('tags', 'social', 'linked_contacts'):
                        params.append(json.dumps(data[field]))
                    else:
                        params.append(data[field])

            if not fields:
                return jsonify({'error': 'no fields to update'}), 400

            fields.append("updated_at = %s")
            params.append(datetime.now().isoformat())
            params.append(contact_id)
            params.append(current_user_id())

            cur.execute(
                f"UPDATE contacts SET {', '.join(fields)} WHERE id = %s AND user_id = %s RETURNING *",
                params
            )
            row = cur.fetchone()
            if not row:
                return jsonify({'error': 'contact not found'}), 404
        conn.commit()
    finally:
        conn.close()

    return jsonify({'status': 'ok', 'contact': _row_to_dict(row)})

@app.route('/api/v1/contacts/<contact_id>', methods=['DELETE'])
@login_required
def api_delete_contact(contact_id):
    """Delete one of the signed-in user's contacts, with its reminders and activity."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contacts WHERE id = %s AND user_id = %s", (contact_id, current_user_id()))
            # Only remove child rows whose contact is gone; a contact owned by someone else still exists
            cur.execute("DELETE FROM reminders r WHERE r.contact_id = %s AND NOT EXISTS (SELECT 1 FROM contacts c WHERE c.id = r.contact_id)", (contact_id,))
            cur.execute("DELETE FROM activities a WHERE a.contact_id = %s AND NOT EXISTS (SELECT 1 FROM contacts c WHERE c.id = a.contact_id)", (contact_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/v1/bulk', methods=['POST'])
@login_required
def api_bulk():
    """Bulk operations on the signed-in user's contacts: delete, tag, untag, export."""
    uid = current_user_id()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'expected a JSON object'}), 400
    action = data.get('action', '')
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'error': 'no contact IDs provided'}), 400

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if action == 'delete':
                cur.execute("DELETE FROM contacts WHERE id = ANY(%s) AND user_id = %s", (ids, uid))
                cur.execute("DELETE FROM reminders r WHERE r.contact_id = ANY(%s) AND NOT EXISTS (SELECT 1 FROM contacts c WHERE c.id = r.contact_id)", (ids,))
                cur.execute("DELETE FROM activities a WHERE a.contact_id = ANY(%s) AND NOT EXISTS (SELECT 1 FROM contacts c WHERE c.id = a.contact_id)", (ids,))
                conn.commit()
                return jsonify({'status': 'ok', 'deleted': len(ids)})

            elif action == 'tag':
                tag = data.get('tag', '').strip()
                if not tag:
                    return jsonify({'error': 'tag required'}), 400
                for cid in ids:
                    cur.execute(
                        """
                        UPDATE contacts
                        SET tags = (
                            SELECT jsonb_agg(DISTINCT x)
                            FROM jsonb_array_elements(tags || %s) x
                        ),
                        updated_at = %s
                        WHERE id = %s AND user_id = %s
                        """,
                        (json.dumps([tag]), datetime.now().isoformat(), cid, uid)
                    )
                conn.commit()
                return jsonify({'status': 'ok', 'tagged': tag})

            elif action == 'untag':
                tag = data.get('tag', '').strip()
                if not tag:
                    return jsonify({'error': 'tag required'}), 400
                for cid in ids:
                    cur.execute(
                        """
                        UPDATE contacts
                        SET tags = COALESCE((
                            SELECT jsonb_agg(x)
                            FROM jsonb_array_elements(tags) x
                            WHERE x != %s::jsonb
                        ), '[]'::jsonb),
                        updated_at = %s
                        WHERE id = %s AND user_id = %s
                        """,
                        (json.dumps(tag), datetime.now().isoformat(), cid, uid)
                    )
                conn.commit()
                return jsonify({'status': 'ok', 'untagged': tag})

            elif action == 'export':
                cur.execute(
                    "SELECT * FROM contacts WHERE id = ANY(%s) AND user_id = %s",
                    (ids, uid)
                )
                rows = cur.fetchall()
                selected = [_row_to_dict(r) for r in rows]
                fmt = data.get('format', 'json')
                if fmt == 'csv':
                    return export_csv(selected)
                elif fmt == 'vcard':
                    return export_vcard(selected)
                else:
                    return jsonify(selected)

            else:
                return jsonify({'error': 'unknown action'}), 400
    finally:
        conn.close()

# ── Duplicate detection ────────────────────────────────────────────────

def _first_names_compatible(a_name, b_name):
    """False when both contacts have clearly different first names (e.g. a family sharing an email).
    "Josh" vs "Joshua" counts as compatible; single-word names can't be compared, so they are too."""
    a_words = (a_name or '').lower().split()
    b_words = (b_name or '').lower().split()
    if len(a_words) < 2 or len(b_words) < 2:
        return True
    a_first, b_first = a_words[0], b_words[0]
    return a_first.startswith(b_first) or b_first.startswith(a_first)

@app.route('/api/v1/duplicates', methods=['GET'])
@login_required
def api_duplicates():
    """Detect potential duplicate contacts using fuzzy name/email/phone matching."""
    try:
        threshold = float(request.args.get('threshold', '0.7'))
    except ValueError:
        return jsonify({'error': 'threshold must be a number'}), 400
    contacts = load_contacts(current_user_id())
    duplicates = []

    for i, a in enumerate(contacts):
        for b in contacts[i+1:]:
            score = 0.0
            reasons = []

            # Name similarity (simple Jaccard on words)
            a_words = set(a.get('name','').lower().split())
            b_words = set(b.get('name','').lower().split())
            if a_words and b_words:
                jaccard = len(a_words & b_words) / len(a_words | b_words)
                if jaccard > 0.5:
                    score = max(score, jaccard)
                    reasons.append(f"name: {jaccard:.0%}")

            # A shared email or phone only means a duplicate if the names could be the same person
            same_person_possible = _first_names_compatible(a.get('name'), b.get('name'))

            # Email match
            a_email = a.get('email','').strip().lower()
            b_email = b.get('email','').strip().lower()
            if same_person_possible and a_email and a_email == b_email:
                score = max(score, 1.0)
                reasons.append("email match")

            # Phone match (digits only)
            a_phone = re.sub(r'\D', '', a.get('phone',''))
            b_phone = re.sub(r'\D', '', b.get('phone',''))
            if same_person_possible and a_phone and a_phone == b_phone:
                score = max(score, 0.95)
                reasons.append("phone match")

            if score >= threshold:
                duplicates.append({
                    'score': round(score, 2),
                    'reasons': reasons,
                    'contacts': [a, b]
                })

    duplicates.sort(key=lambda x: -x['score'])
    return jsonify(duplicates)

# ── Import/Export ──────────────────────────────────────────────────────

@app.route('/api/v1/import', methods=['POST'])
@login_required
def api_import():
    """Import contacts from JSON, CSV, or vCard format."""
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'no file provided'}), 400

    filename = file.filename.lower()
    content = file.read().decode('utf-8', errors='replace')
    imported = []

    if filename.endswith('.json'):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return jsonify({'error': f'invalid JSON: {e}'}), 400
        if isinstance(data, dict):
            data = data.get('contacts')
        if isinstance(data, list):
            imported = [c for c in data if isinstance(c, dict)]
            for c in imported:
                c['id'] = c.get('id') or _new_id()

    elif filename.endswith('.csv'):
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            contact = {
                'id': _new_id(),
                'name': row.get('name', row.get('Name', row.get('NAME', ''))).strip(),
                'phone': row.get('phone', row.get('Phone', row.get('PHONE', ''))).strip(),
                'email': row.get('email', row.get('Email', row.get('EMAIL', ''))).strip(),
                'address': row.get('address', row.get('Address', row.get('ADDRESS', ''))).strip(),
                'tags': [t.strip() for t in row.get('tags', row.get('Tags', '')).split(',') if t.strip()],
                'notes': row.get('notes', row.get('Notes', '')).strip(),
                'avatar': '',
                'birthday': row.get('birthday', row.get('Birthday', '')),
                'social': {},
                'linked_contacts': [],
                'createdAt': datetime.now().isoformat(),
                'updatedAt': datetime.now().isoformat()
            }
            if contact['name']:
                imported.append(contact)

    elif filename.endswith('.vcf'):
        imported = parse_vcard(content)

    if not imported:
        return jsonify({'error': 'no valid contacts found in file'}), 400

    # Merge with existing: skip contacts this user already has. An id held by another
    # account is replaced with a fresh one so the import never touches their data.
    uid = current_user_id()
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM contacts WHERE user_id = %s", (uid,))
            existing_ids = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT id FROM contacts WHERE id = ANY(%s)", ([c['id'] for c in imported],))
            taken_ids = {r[0] for r in cur.fetchall()}
            new_count = 0
            for c in imported:
                if c['id'] in existing_ids:
                    continue
                if c['id'] in taken_ids:
                    c['id'] = _new_id()
                cur.execute(
                    """
                    INSERT INTO contacts
                    (id, name, phone, email, address, tags, notes, avatar, birthday,
                     social, linked_contacts, starred, created_at, updated_at, company, title, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        c['id'],
                        c.get('name', ''),
                        c.get('phone', ''),
                        c.get('email', ''),
                        c.get('address', ''),
                        json.dumps(c.get('tags', [])),
                        c.get('notes', ''),
                        c.get('avatar', ''),
                        c.get('birthday', ''),
                        json.dumps(c.get('social', {})),
                        json.dumps(c.get('linked_contacts', [])),
                        bool(c.get('starred', False)),
                        c.get('createdAt', datetime.now().isoformat()),
                        c.get('updatedAt', datetime.now().isoformat()),
                        c.get('company', ''),
                        c.get('title', ''),
                        uid,
                    )
                )
                existing_ids.add(c['id'])
                new_count += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'import failed: {str(e)}'}), 500
    finally:
        conn.close()

    return jsonify({'status': 'ok', 'imported': len(imported), 'new': new_count})


def parse_vcard(content):
    """Basic vCard 3.0/4.0 parser."""
    contacts = []
    current = None
    for raw_line in content.split('\n'):
        # Handle folded lines (starts with space or tab) — append to previous line
        if raw_line.startswith(' ') or raw_line.startswith('\t'):
            if current and current.get('_last_key'):
                current[current['_last_key']] += raw_line.strip()
            continue

        line = raw_line.strip()

        if line.startswith('BEGIN:VCARD'):
            current = {
                'id': _new_id(),
                'name': '', 'phone': '', 'email': '', 'address': '',
                'tags': [], 'notes': '', 'avatar': '', 'birthday': '',
                'social': {}, 'linked_contacts': [],
                'createdAt': datetime.now().isoformat(),
                'updatedAt': datetime.now().isoformat(),
                '_last_key': None
            }
        elif line.startswith('END:VCARD'):
            if current and current['name']:
                contacts.append(current)
            current = None
        elif current:
            # Parse common vCard fields
            if line.startswith('FN:'):
                current['name'] = line[3:].strip()
                current['_last_key'] = 'name'
            elif line.startswith('N:') and not current['name']:
                # N:Family;Given;Middle;Prefix;Suffix — use Given Family
                parts = line[2:].split(';')
                given = parts[1].strip() if len(parts) > 1 else ''
                family = parts[0].strip() if len(parts) > 0 else ''
                current['name'] = f"{given} {family}".strip()
                current['_last_key'] = 'name'
            elif line.startswith('TEL'):
                # TEL;TYPE=CELL:1234567890
                val = line.split(':', 1)[1].strip() if ':' in line else line
                if val and not current['phone']:
                    current['phone'] = val
                current['_last_key'] = 'phone'
            elif line.startswith('EMAIL'):
                val = line.split(':', 1)[1].strip() if ':' in line else line
                if val and not current['email']:
                    current['email'] = val
                current['_last_key'] = 'email'
            elif line.startswith('ADR'):
                val = line.split(':', 1)[1].strip() if ':' in line else line
                if val and not current['address']:
                    parts = val.split(';')
                    street = parts[2].strip() if len(parts) > 2 else ''
                    city = parts[3].strip() if len(parts) > 3 else ''
                    region = parts[4].strip() if len(parts) > 4 else ''
                    code = parts[5].strip() if len(parts) > 5 else ''
                    country = parts[6].strip() if len(parts) > 6 else ''
                    addr = ' '.join(filter(None, [street, city, region, code, country]))
                    current['address'] = addr
                current['_last_key'] = 'address'
            elif line.startswith('BDAY'):
                val = line.split(':', 1)[1].strip() if ':' in line else line
                if val and not current['birthday']:
                    current['birthday'] = val
                current['_last_key'] = 'birthday'
            elif line.startswith('NOTE'):
                val = line.split(':', 1)[1].strip() if ':' in line else line
                if val:
                    current['notes'] = (current['notes'] + ' ' + val).strip() if current['notes'] else val
                current['_last_key'] = 'notes'
            elif line.startswith('URL'):
                val = line.split(':', 1)[1].strip() if ':' in line else line
                if val and not current['avatar']:
                    current['avatar'] = val
                current['_last_key'] = 'avatar'
            else:
                current['_last_key'] = None

    return contacts


def export_csv(contacts):
    """Export selected contacts as CSV."""
    output = io.StringIO()
    fieldnames = ['name', 'phone', 'email', 'address', 'tags', 'notes', 'birthday']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for c in contacts:
        writer.writerow({
            'name': c.get('name',''),
            'phone': c.get('phone',''),
            'email': c.get('email',''),
            'address': c.get('address',''),
            'tags': ', '.join(c.get('tags',[])),
            'notes': c.get('notes',''),
            'birthday': c.get('birthday','')
        })
    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    return send_file(mem, mimetype='text/csv', as_attachment=True,
                     download_name='rolodex_contacts.csv')


def export_vcard(contacts):
    """Export selected contacts as vCard 3.0."""
    lines = []
    for c in contacts:
        lines.append('BEGIN:VCARD')
        lines.append('VERSION:3.0')
        lines.append(f"FN:{c.get('name','')}")
        if c.get('phone'):
            lines.append(f"TEL:{c.get('phone','')}")
        if c.get('email'):
            lines.append(f"EMAIL:{c.get('email','')}")
        if c.get('address'):
            lines.append(f"ADR:{c.get('address','')}")
        if c.get('birthday'):
            lines.append(f"BDAY:{c.get('birthday','')}")
        if c.get('notes'):
            # Fold long notes
            note = c['notes'].replace('\n', '\\n')
            lines.append(f"NOTE:{note}")
        lines.append('END:VCARD')
        lines.append('')

    mem = io.BytesIO('\n'.join(lines).encode('utf-8'))
    return send_file(mem, mimetype='text/vcard', as_attachment=True,
                     download_name='rolodex_contacts.vcf')

# ── Fireworks AI Integration ────────────────────────────────────────────

@app.route('/api/v1/ai/enrich', methods=['POST'])
@login_required
def ai_enrich():
    """Use Fireworks AI to enrich a contact: suggest tags, find duplicates."""
    data = request.get_json(silent=True)
    if not data or not data.get('name'):
        return jsonify({'error': 'name required'}), 400

    prompt = (
        "You are a contact management AI. Output ONLY valid JSON with these exact keys:\n"
        "{\"tags\":[\"example1\",\"example2\"],\"summary\":\"Example summary.\",\"category\":\"professional\"}\n\n"
        "Contact:\n"
        f"  Name: {data.get('name','')}\n"
        f"  Phone: {data.get('phone','')}\n"
        f"  Email: {data.get('email','')}\n"
        f"  Address: {data.get('address','')}\n"
        f"  Existing tags: {', '.join(data.get('tags',[]))}\n"
        f"  Notes: {data.get('notes','')}\n\n"
        "Return ONLY the JSON object. Do not include the example values. Generate your own tags, summary, and category."
    )
    try:
        payload = json.dumps({
            "model": FIREWORKS_MODEL,
            "messages": [
                {"role": "system", "content": "You are a JSON-only API. Output ONLY valid JSON matching the exact schema. No explanations, no markdown, no code fences."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.1
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{FIREWORKS_API}/chat/completions",
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {FIREWORKS_API_KEY}'
            }
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        raw = result['choices'][0]['message']['content'].strip()
        # Extract JSON from response - handle various formats
        raw = extract_json(raw)
        enrichment = json.loads(raw)
        return jsonify({
            'status': 'ok',
            'suggested_tags': enrichment.get('tags', []),
            'summary': enrichment.get('summary', ''),
            'category': enrichment.get('category', 'other')
        })

    except Exception as e:
        return jsonify({'error': f'AI enrichment failed: {str(e)}'}), 500


def extract_json(text):
    """Extract valid JSON from model response, handling various formats."""
    if not text:
        return '{}'
    text = text.strip()
    # Remove markdown fences
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0].strip()
    elif '```' in text:
        text = text.split('```')[1].split('```')[0].strip()
    # Find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        return text[start:end+1]
    return '{}'


@app.route('/api/v1/ai/auto-categorize', methods=['POST'])
@login_required
def ai_auto_categorize():
    """Auto-categorize all untagged contacts."""
    contacts = load_contacts(current_user_id())
    untagged = [c for c in contacts if not c.get('tags')]

    if not untagged:
        return jsonify({'status': 'ok', 'categorized': 0, 'message': 'All contacts already have tags'})

    results = []
    for contact in untagged[:10]:  # Limit to 10 per call to avoid timeout
        prompt = (
            "Suggest 2-4 relevant tags for this contact. Respond ONLY with a JSON array of strings.\n\n"
            f"Name: {contact.get('name','')}\n"
            f"Phone: {contact.get('phone','')}\n"
            f"Email: {contact.get('email','')}\n"
            f"Address: {contact.get('address','')}\n"
            f"Notes: {contact.get('notes','')}"
        )

        try:
            payload = json.dumps({
                "model": FIREWORKS_MODEL,
                "messages": [
                    {"role": "system", "content": "Respond only with a JSON array of tag strings."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 100,
                "temperature": 0.3
            }).encode('utf-8')

            req = urllib.request.Request(
                f"{FIREWORKS_API}/chat/completions",
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {FIREWORKS_API_KEY}'
                }
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())

            raw = result['choices'][0]['message']['content'].strip()
            if '```json' in raw:
                raw = raw.split('```json')[1].split('```')[0].strip()
            elif '```' in raw:
                raw = raw.split('```')[1].split('```')[0].strip()

            suggested = json.loads(raw)
            if isinstance(suggested, list):
                contact['tags'] = [t for t in suggested if isinstance(t, str)][:5]
                contact['updatedAt'] = datetime.now().isoformat()
                results.append({'name': contact['name'], 'tags': contact['tags']})

        except Exception:
            pass

    # Save updated tags back to DB
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            for contact in untagged[:10]:
                if contact.get('tags'):
                    cur.execute(
                        "UPDATE contacts SET tags = %s, updated_at = %s WHERE id = %s AND user_id = %s",
                        (json.dumps(contact['tags']), contact['updatedAt'], contact['id'], current_user_id())
                    )
        conn.commit()
    finally:
        conn.close()

    return jsonify({'status': 'ok', 'categorized': len(results), 'results': results})


@app.route('/api/v1/ai/search', methods=['POST'])
@login_required
def ai_search():
    """Natural language search using AI."""
    data = request.get_json(silent=True)
    query = (data.get('query', '') if data else '').strip()
    if not query:
        return jsonify({'error': 'query required'}), 400

    contacts = load_contacts(current_user_id())
    if not contacts:
        return jsonify([])

    # Prepare compact contact data
    contact_summaries = []
    for c in contacts:
        contact_summaries.append(
            f"ID:{c['id']} Name:{c.get('name','')} Phone:{c.get('phone','')} "
            f"Email:{c.get('email','')} Address:{c.get('address','')} "
            f"Tags:{','.join(c.get('tags',[]))} Notes:{c.get('notes','')}"
        )

    prompt = (
        f"User search query: \"{query}\"\n\n"
        f"Contacts database:\n" + '\n'.join(contact_summaries) + "\n\n"
        "Return ONLY a JSON array of contact IDs that match the query, ranked by relevance. "
        "Consider name, phone, email, address, tags, and notes. "
        "If nothing matches, return an empty array []. "
        "Respond ONLY with the JSON array."
    )

    try:
        payload = json.dumps({
            "model": FIREWORKS_MODEL,
            "messages": [
                {"role": "system", "content": "You are a smart contact search assistant. Return only JSON arrays."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,
            "temperature": 0.1
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{FIREWORKS_API}/chat/completions",
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {FIREWORKS_API_KEY}'
            }
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        raw = result['choices'][0]['message']['content'].strip()
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0].strip()
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0].strip()

        matched_ids = json.loads(raw)
        if not isinstance(matched_ids, list):
            matched_ids = []

        # Return full contact objects in ranked order
        contact_map = {c['id']: c for c in contacts}
        results = [contact_map[cid] for cid in matched_ids if cid in contact_map]
        return jsonify(results)

    except Exception as e:
        return jsonify({'error': f'AI search failed: {str(e)}'}), 500


# ── Tags discovery ──────────────────────────────────────────────────────

@app.route('/api/v1/tags', methods=['GET'])
@login_required
def api_tags():
    """Get all unique tags across contacts."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tags FROM contacts WHERE user_id = %s", (current_user_id(),))
            all_tags = {}
            for row in cur.fetchall():
                tags = row[0]
                if isinstance(tags, str):
                    tags = json.loads(tags)
                if isinstance(tags, list):
                    for tag in tags:
                        tag = tag.strip() if isinstance(tag, str) else ''
                        if tag:
                            all_tags[tag] = all_tags.get(tag, 0) + 1
            # Sort by frequency desc, then alphabetically
            sorted_tags = sorted(all_tags.items(), key=lambda x: (-x[1], x[0]))
            return jsonify([{'name': t, 'count': c} for t, c in sorted_tags])
    finally:
        conn.close()


# ── Merge ──────────────────────────────────────────────────────────────

@app.route('/api/v1/merge', methods=['POST'])
@login_required
def api_merge():
    """Merge two contacts: keep all data from primary, overwrite with secondary's non-empty fields, then delete secondary."""
    data = request.get_json(silent=True)
    if not data or not data.get('primary_id') or not data.get('secondary_id'):
        return jsonify({'error': 'primary_id and secondary_id required'}), 400
    if data['primary_id'] == data['secondary_id']:
        # Merging a contact into itself would delete it
        return jsonify({'error': 'cannot merge a contact with itself'}), 400

    contacts = load_contacts(current_user_id())
    primary = next((c for c in contacts if c['id'] == data['primary_id']), None)
    secondary = next((c for c in contacts if c['id'] == data['secondary_id']), None)

    if not primary or not secondary:
        return jsonify({'error': 'one or both contacts not found'}), 404

    # Field-level merge: secondary's non-empty values win for specified fields
    merge_fields = data.get('fields', ['name', 'phone', 'email', 'address', 'tags', 'notes', 'avatar', 'birthday', 'social', 'company', 'title'])
    for field in merge_fields:
        if field == 'tags':
            # Merge tags from both, deduplicate
            combined = list(dict.fromkeys(primary.get('tags', []) + secondary.get('tags', [])))
            primary['tags'] = combined
        elif field == 'social':
            primary_social = primary.get('social', {}) or {}
            secondary_social = secondary.get('social', {}) or {}
            primary_social.update(secondary_social)
            primary['social'] = primary_social
        elif field == 'linked_contacts':
            combined = list(dict.fromkeys(primary.get('linked_contacts', []) + secondary.get('linked_contacts', [])))
            # Remove references to the secondary contact itself
            primary['linked_contacts'] = [cid for cid in combined if cid != secondary['id']]
        else:
            val = secondary.get(field)
            if val:
                primary[field] = val

    primary['updatedAt'] = datetime.now().isoformat()

    # Remove secondary from contacts list
    contacts = [c for c in contacts if c['id'] != secondary['id']]

    # Also update any linked_contacts that reference the secondary
    for c in contacts:
        if secondary['id'] in c.get('linked_contacts', []):
            c['linked_contacts'] = [primary['id'] if l == secondary['id'] else l for l in c['linked_contacts']]

    # Move the secondary's reminders and activity to the primary before it is removed
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            for table in ('reminders', 'activities'):
                cur.execute(f"UPDATE {table} SET contact_id = %s WHERE contact_id = %s", (primary['id'], secondary['id']))
        conn.commit()
    finally:
        conn.close()

    # Persist to DB
    save_contacts(contacts, current_user_id())
    return jsonify({'status': 'ok', 'contact': primary})


# ── Reminders and activity log (per contact) ───────────────────────────

def _db_rows(sql, params=()):
    """Run one statement, commit, and return any returned rows as dicts with ISO timestamps."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        conn.commit()
    finally:
        conn.close()
    for r in rows:
        if isinstance(r.get('created_at'), datetime):
            r['created_at'] = r['created_at'].isoformat()
    return rows

@app.route('/api/v1/contacts/<contact_id>/reminders', methods=['GET'])
@login_required
def api_get_reminders(contact_id):
    rows = _db_rows(
        "SELECT r.id, r.contact_id, r.title, r.description, r.due_date, r.completed, r.created_at "
        "FROM reminders r JOIN contacts c ON c.id = r.contact_id "
        "WHERE r.contact_id = %s AND c.user_id = %s "
        "ORDER BY r.completed, r.due_date, r.created_at",
        (contact_id, current_user_id()))
    return jsonify({'reminders': rows})

@app.route('/api/v1/contacts/<contact_id>/reminders', methods=['POST'])
@login_required
def api_add_reminder(contact_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not _text(data, 'title') or not _text(data, 'due_date'):
        return jsonify({'error': 'title and due_date are required'}), 400
    # The WHERE clause only matches a contact the signed-in user owns, so others return no row
    rows = _db_rows(
        "INSERT INTO reminders (id, contact_id, title, description, due_date, completed, created_at) "
        "SELECT %s, id, %s, %s, %s, FALSE, %s FROM contacts WHERE id = %s AND user_id = %s "
        "RETURNING id, contact_id, title, description, due_date, completed, created_at",
        (_new_id(), _text(data, 'title'), _text(data, 'description'), _text(data, 'due_date'),
         datetime.now(), contact_id, current_user_id()))
    if not rows:
        return jsonify({'error': 'contact not found'}), 404
    return jsonify(rows[0]), 201

@app.route('/api/v1/reminders/<reminder_id>/complete', methods=['POST'])
@login_required
def api_complete_reminder(reminder_id):
    rows = _db_rows(
        "UPDATE reminders SET completed = TRUE WHERE id = %s "
        "AND contact_id IN (SELECT id FROM contacts WHERE user_id = %s) "
        "RETURNING id, contact_id, title, description, due_date, completed, created_at",
        (reminder_id, current_user_id()))
    if not rows:
        return jsonify({'error': 'reminder not found'}), 404
    return jsonify(rows[0])

@app.route('/api/v1/reminders/<reminder_id>', methods=['DELETE'])
@login_required
def api_delete_reminder(reminder_id):
    rows = _db_rows(
        "DELETE FROM reminders WHERE id = %s "
        "AND contact_id IN (SELECT id FROM contacts WHERE user_id = %s) RETURNING id",
        (reminder_id, current_user_id()))
    if not rows:
        return jsonify({'error': 'reminder not found'}), 404
    return jsonify({'status': 'ok'})

@app.route('/api/v1/contacts/<contact_id>/activities', methods=['GET'])
@login_required
def api_get_activities(contact_id):
    rows = _db_rows(
        "SELECT a.id, a.contact_id, a.type, a.subject, a.notes, a.timestamp, a.created_at "
        "FROM activities a JOIN contacts c ON c.id = a.contact_id "
        "WHERE a.contact_id = %s AND c.user_id = %s "
        "ORDER BY a.timestamp DESC, a.created_at DESC",
        (contact_id, current_user_id()))
    return jsonify({'activities': rows})

@app.route('/api/v1/contacts/<contact_id>/activities', methods=['POST'])
@login_required
def api_add_activity(contact_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not _text(data, 'type') or not _text(data, 'subject'):
        return jsonify({'error': 'type and subject are required'}), 400
    rows = _db_rows(
        "INSERT INTO activities (id, contact_id, type, subject, notes, timestamp, created_at) "
        "SELECT %s, id, %s, %s, %s, %s, %s FROM contacts WHERE id = %s AND user_id = %s "
        "RETURNING id, contact_id, type, subject, notes, timestamp, created_at",
        (_new_id(), _text(data, 'type'), _text(data, 'subject'), _text(data, 'notes'),
         _text(data, 'timestamp') or datetime.now().isoformat(), datetime.now(), contact_id, current_user_id()))
    if not rows:
        return jsonify({'error': 'contact not found'}), 404
    return jsonify(rows[0]), 201


# ── Run ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=DEBUG)
