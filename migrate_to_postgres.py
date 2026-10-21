#!/usr/bin/env python3
"""Migrate contacts from JSON to PostgreSQL."""
import json
import os
import psycopg2
import psycopg2.extras

DB_CONFIG = {
    'host': os.environ.get('ROLODEX_DB_HOST', 'localhost'),
    'port': int(os.environ.get('ROLODEX_DB_PORT', '5432')),
    'dbname': os.environ.get('ROLODEX_DB_NAME', 'rolodex'),
    'user': os.environ.get('ROLODEX_DB_USER', 'rolodex'),
    'password': os.environ.get('ROLODEX_DB_PASSWORD', 'rolodex123'),
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTACTS_PATH = os.path.join(BASE_DIR, 'contacts.json')

CREATE_TABLE_SQL = """
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
);
"""

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        print("Table 'contacts' initialized.")
    finally:
        conn.close()

def migrate_json():
    if not os.path.exists(CONTACTS_PATH):
        print("No contacts.json found — nothing to migrate.")
        return

    with open(CONTACTS_PATH) as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        print("contacts.json is empty or invalid — nothing to migrate.")
        return

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            inserted = 0
            skipped = 0
            for c in data:
                cid = c.get('id')
                if not cid:
                    skipped += 1
                    continue
                # Check if already exists
                cur.execute("SELECT 1 FROM contacts WHERE id = %s", (cid,))
                if cur.fetchone():
                    skipped += 1
                    continue

                cur.execute(
                    """
                    INSERT INTO contacts
                    (id, name, phone, email, address, tags, notes, avatar, birthday,
                     social, linked_contacts, starred, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        cid,
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
                        c.get('createdAt', '1970-01-01T00:00:00'),
                        c.get('updatedAt', '1970-01-01T00:00:00')
                    )
                )
                inserted += 1
        conn.commit()
        print(f"Migrated {inserted} contacts, skipped {skipped} (already exist or missing id).")
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    migrate_json()
