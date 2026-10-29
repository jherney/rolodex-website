#!/usr/bin/env python3
"""Import contacts.json into Postgres for one account, or adopt contacts that have no owner.

    python3 migrate_to_postgres.py --owner you@example.com                  # import ./contacts.json
    python3 migrate_to_postgres.py --owner you@example.com --file old.json
    python3 migrate_to_postgres.py --claim-orphans --owner you@example.com

Connects exactly like the app (DATABASE_URL / POSTGRES_URL, else ROLODEX_DB_*), and importing
the app brings the schema up to date first. The account must exist: sign up at / before running.
Exit codes: 0 done, 1 bad input file, 2 no such account (or bad arguments).
"""
import argparse
import json
import os
import sys

from app import get_db_conn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def owner_id(cur, email):
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    if not row:
        print(f"migrate: no account for {email}; sign up at / first, then rerun", file=sys.stderr)
        sys.exit(2)
    return row[0]


def claim_orphans(cur, uid, email):
    # One statement, so a failure leaves every row as it was
    cur.execute("UPDATE contacts SET user_id = %s WHERE user_id IS NULL", (uid,))
    print(f"migrate: assigned {cur.rowcount} contacts with no owner to {email}")


def import_json(cur, uid, email, path):
    if not os.path.exists(path):
        print(f"migrate: {path} not found; nothing to import", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"migrate: {path} must hold a JSON list of contacts", file=sys.stderr)
        sys.exit(1)

    inserted = skipped = 0
    for c in data:
        cid = c.get('id') if isinstance(c, dict) else None
        if not cid:
            skipped += 1
            continue
        cur.execute(
            """
            INSERT INTO contacts
            (id, name, phone, email, address, tags, notes, avatar, birthday,
             social, linked_contacts, starred, created_at, updated_at, company, title, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
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
                c.get('updatedAt', '1970-01-01T00:00:00'),
                c.get('company', ''),
                c.get('title', ''),
                uid,
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1
    print(f"migrate: imported {inserted} contacts for {email}, skipped {skipped} (already exist or missing id)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--owner', required=True, help='email of the account that will own the contacts')
    parser.add_argument('--claim-orphans', action='store_true',
                        help='adopt contacts saved before accounts existed instead of importing a file')
    parser.add_argument('--file', default=os.path.join(BASE_DIR, 'contacts.json'),
                        help='JSON file to import (default: contacts.json next to this script)')
    args = parser.parse_args()
    # Sign-up stores emails lowercased
    email = args.owner.strip().lower()

    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            uid = owner_id(cur, email)
            if args.claim_orphans:
                claim_orphans(cur, uid, email)
            else:
                import_json(cur, uid, email, args.file)
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
