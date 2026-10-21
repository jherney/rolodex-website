#!/usr/bin/env python3
"""
Small automated test harness for the Rolodex Add button flow (API level).
It exercises the same per-contact endpoints the UI uses:
- POST /api/v1/contacts (add)
- PUT /api/v1/contacts/<id> (update)
- DELETE /api/v1/contacts/<id> (cleanup)

It only touches the contacts it creates; existing contacts are left alone.

Requirements: Python 3 standard library only (no extra deps).
Server must be running on localhost:5000 (override with BASE_URL).
"""
import json
import os
import urllib.request

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')


def call(method, path, payload=None):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode() or 'null')
    except Exception as e:
        print(f"[ERR] {method} {path} failed: {e}")
        return None


def find_contact(contact_id):
    contacts = call('GET', '/api/v1/contacts') or []
    return next((c for c in contacts if c.get('id') == contact_id), None)


def run():
    print("Rolodex Add-button harness starting against", BASE)
    created = []
    try:
        # 1) add A
        a = call('POST', '/api/v1/contacts', {"name": "Harness A", "phone": "555-0009", "tags": ["friends"]})
        a_id = a and a['contact']['id']
        created.append(a_id)
        print("Added A present:", bool(a_id and find_contact(a_id)))

        # 2) add B
        b = call('POST', '/api/v1/contacts', {"name": "Harness B", "phone": "555-0010", "tags": ["family"]})
        b_id = b and b['contact']['id']
        created.append(b_id)
        print("Added B present:", bool(b_id and find_contact(b_id)))

        # 3) update A
        call('PUT', f'/api/v1/contacts/{a_id}', {"phone": "555-9999"})
        updated = find_contact(a_id)
        print("Updated A present with new phone:", bool(updated and updated.get('phone') == '555-9999'))
    finally:
        for contact_id in filter(None, created):
            call('DELETE', f'/api/v1/contacts/{contact_id}')
    print("Harness finished")


if __name__ == '__main__':
    run()
