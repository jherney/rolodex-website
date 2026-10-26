#!/usr/bin/env python3
"""
Rolodex API integration smoke tests.
Tests all production endpoints end-to-end.

Usage:
    python3 tests/api_integration_smoke.py            # against localhost:5000
    BASE_URL=http://myhost:8080 python3 tests/api_integration_smoke.py
"""
import json
import urllib.request
import urllib.error
import sys
import os

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
PASS = 0
FAIL = 0


def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f'  ✓ {name}')
    except AssertionError as e:
        FAIL += 1
        print(f'  ✗ {name}: {e}')
    except Exception as e:
        FAIL += 1
        print(f'  ✗ {name}: {type(e).__name__}: {e}')


import http.cookiejar
import time

def new_opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

OPENER = new_opener()


def request(method, path, body=None, expect=200, opener=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={'Content-Type': 'application/json'} if body is not None else {},
                                 method=method)
    try:
        resp = (opener or OPENER).open(req, timeout=10)
    except urllib.error.HTTPError as e:
        resp = e
    status = resp.code if isinstance(resp, urllib.error.HTTPError) else resp.status
    assert status == expect, f'expected {expect}, got {status}'
    ct = resp.headers.get('content-type', '')
    text = resp.read().decode()
    if 'json' in ct:
        return json.loads(text)
    return text


def sign_up(email, password='correct-horse-battery'):
    """Create an account and return an opener that holds its session cookie."""
    opener = new_opener()
    request('POST', '/api/v1/auth/signup', {'email': email, 'password': password}, expect=201, opener=opener)
    return opener


def main():
    print(f'Rolodex API Integration Smoke Tests')
    print(f'Target: {BASE}')
    print()

    # Each run uses a fresh account, so test data never mixes with real accounts
    global OPENER
    run_id = str(int(time.time() * 1000))
    OPENER = sign_up(f'smoke-{run_id}@example.test')
    other = sign_up(f'smoke-other-{run_id}@example.test')
    anon = new_opener()

    print('[Accounts]')
    test('signed-out contact list returns 401', lambda: request('GET', '/api/v1/contacts', expect=401, opener=anon))
    test('signed-out /get_contacts returns 401', lambda: request('GET', '/get_contacts', expect=401, opener=anon))
    test('wrong password returns 401', lambda: request('POST', '/api/v1/auth/login', {'email': f'smoke-{run_id}@example.test', 'password': 'wrong-password-here'}, expect=401, opener=anon))
    test('duplicate signup returns 409 without revealing the account', lambda: assert_equal(request('POST', '/api/v1/auth/signup', {'email': f'smoke-{run_id}@example.test', 'password': 'correct-horse-battery'}, expect=409, opener=anon)['error'], "Couldn't create an account with that email. If you already have one, sign in instead."))
    test('GET /api/v1/auth/me is empty when signed out', lambda: assert_equal(request('GET', '/api/v1/auth/me', opener=anon)['email'], None))
    test('GET /api/v1/auth/me returns the signed-in email', lambda: assert_equal(request('GET', '/api/v1/auth/me', opener=OPENER)['email'], f'smoke-{run_id}@example.test'))

    isolation = {}

    def create_isolation_contact():
        isolation['id'] = request('POST', '/api/v1/contacts', {'name': 'Isolation Check'}, expect=201)['contact']['id']

    test('create contact as first account', create_isolation_contact)
    test('other account cannot see the contact', lambda: assert_equal(
        [c for c in request('GET', '/api/v1/contacts', opener=other) if c['id'] == isolation['id']], []))
    test('other account cannot edit the contact', lambda: request(
        'PUT', f"/api/v1/contacts/{isolation['id']}", {'name': 'Hijacked'}, expect=404, opener=other))
    test('other account cannot add a reminder to the contact', lambda: request(
        'POST', f"/api/v1/contacts/{isolation['id']}/reminders", {'title': 'x', 'due_date': '2026-12-01'}, expect=404, opener=other))
    test('other account cannot read the contact reminders', lambda: assert_equal(
        request('GET', f"/api/v1/contacts/{isolation['id']}/reminders", opener=other)['reminders'], []))
    test('other account delete does not remove the contact', lambda: (
        request('DELETE', f"/api/v1/contacts/{isolation['id']}", expect=200, opener=other),
        assert_equal(any(c['id'] == isolation['id'] for c in request('GET', '/api/v1/contacts', opener=OPENER)), True)))
    test('owner can delete the contact', lambda: request('DELETE', f"/api/v1/contacts/{isolation['id']}", expect=200, opener=OPENER))

    # ── 1. Health & Readiness ──────────────────────────────────────────
    print('[Health]')
    test('GET /health returns healthy', lambda: (
        assert_equal(request('GET', '/health')['status'], 'healthy')
    ))
    test('GET /ready returns ready', lambda: (
        assert_equal(request('GET', '/ready')['status'], 'ready')
    ))

    # ── 2. Static files ────────────────────────────────────────────────
    print('[Static Files]')
    test('GET / returns HTML', lambda: (
        assert_in('<!doctype html>', request('GET', '/', expect=200).lower())
    ))
    test('GET /styles.css returns CSS', lambda: (
        assert_in(':root', request('GET', '/styles.css', expect=200))
    ))
    test('GET /app.js returns JS', lambda: (
        assert_in('function', request('GET', '/app.js', expect=200))
    ))
    test('GET /manifest.json returns PWA manifest', lambda: (
        assert_equal(request('GET', '/manifest.json')['short_name'], 'Rolodex')
    ))

    # ── 3. Legacy API ──────────────────────────────────────────────────
    print('[Legacy API]')
    test('GET /get_contacts returns list', lambda: (
        assert_isinstance(request('GET', '/get_contacts'), list)
    ))
    # Never post a real list here: /save_contacts replaces the whole contacts table
    def save_contacts_rejects_non_list():
        request('POST', '/save_contacts', {'not': 'a list'}, expect=400)
    test('POST /save_contacts rejects non-list', save_contacts_rejects_non_list)

    # ── 4. v1 API — CRUD ──────────────────────────────────────────────
    print('[v1 API — CRUD]')
    created_id = None

    def create_test_contact():
        nonlocal created_id
        result = request('POST', '/api/v1/contacts', {
            'name': 'Integration Test',
            'phone': '555-000-0000',
            'email': 'test@integrate.com',
            'tags': ['test', 'integration'],
            'birthday': '1990-01-01',
            'notes': 'Created by smoke test'
        }, expect=201)
        assert_equal(result['status'], 'ok')
        created_id = result['contact']['id']
        assert_isinstance(created_id, str)
    test('POST /api/v1/contacts creates contact', create_test_contact)

    def list_contacts():
        contacts = request('GET', '/api/v1/contacts')
        assert_isinstance(contacts, list)
        assert_gt(len(contacts), 0)
    test('GET /api/v1/contacts lists contacts', list_contacts)

    def search_contacts():
        results = request('GET', '/api/v1/contacts?search=integration')
        assert_gt(len(results), 0)
    test('GET /api/v1/contacts?search= works', search_contacts)

    def tag_filter():
        results = request('GET', '/api/v1/contacts?tag=test')
        assert_gt(len(results), 0)
    test('GET /api/v1/contacts?tag= works', tag_filter)

    def update_contact():
        nonlocal created_id
        result = request('PUT', f'/api/v1/contacts/{created_id}', {
            'name': 'Updated Test',
            'phone': '555-111-1111'
        })
        assert_equal(result['contact']['name'], 'Updated Test')
    test('PUT /api/v1/contacts/:id updates contact', update_contact)

    def get_tags():
        tags = request('GET', '/api/v1/tags')
        assert_isinstance(tags, list)
        tag_names = [t['name'] for t in tags]
        assert_in('test', tag_names)
    test('GET /api/v1/tags returns all tags', get_tags)

    def delete_contact():
        nonlocal created_id
        result = request('DELETE', f'/api/v1/contacts/{created_id}')
        assert_equal(result['status'], 'ok')
    test('DELETE /api/v1/contacts/:id deletes contact', delete_contact)

    # ── 5. Duplicate detection ─────────────────────────────────────────
    print('[Duplicate Detection]')
    def find_dupes():
        result = request('GET', '/api/v1/duplicates')
        assert_isinstance(result, list)
    test('GET /api/v1/duplicates returns list', find_dupes)

    # ── 5b. Import ─────────────────────────────────────────────────────
    print('[Import]')
    import_opener = sign_up(f'smoke-import-{run_id}@example.test')

    def upload_import(filename, data):
        boundary = f'----rolodex-smoke-{time.time_ns()}'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        req = urllib.request.Request(BASE + '/api/v1/import', data=body, method='POST',
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        return json.loads(import_opener.open(req, timeout=10).read().decode())

    ann_vcf = b'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ann Lee\r\nTEL:5551234\r\nEMAIL:ann@x.test\r\nEND:VCARD\r\n'
    test('vCard import creates the contact', lambda: assert_equal(upload_import('a.vcf', ann_vcf)['new'], 1))
    test('re-importing the same vCard adds nothing', lambda: (
        assert_equal(upload_import('a.vcf', ann_vcf)['new'], 0),
        assert_equal(len(request('GET', '/api/v1/contacts', opener=import_opener)), 1)))
    test('re-import reports the skipped duplicate', lambda: assert_equal(
        upload_import('a.vcf', ann_vcf)['skipped_duplicates'], 1))
    test('CSV from Excel (UTF-8 BOM) imports the name column', lambda: assert_equal(
        upload_import('b.csv', b'\xef\xbb\xbfName,Phone\r\nBob Ray,555\r\n')['new'], 1))
    test('short CSV row does not crash the import', lambda: assert_equal(
        upload_import('c.csv', b'name,phone,tags\nCara,5550001\n')['new'], 1))
    test('duplicates within one file are imported once', lambda: (
        assert_equal(upload_import('d.csv', b'name,email\nDan Fox,dan@x.test\nDaniel Fox,dan@x.test\n')['new'], 1),
        assert_equal(upload_import('d.csv', b'name,email\nDan Fox,dan@x.test\n')['skipped_duplicates'], 1)))
    test('same name with a different email is imported and flagged as possible', lambda: (
        assert_equal(upload_import('e.csv', b'name,email\nBob Ray,other@x.test\n')['new'], 1),
        assert_equal(upload_import('f.csv', b'name,email\nBob Ray,third@x.test\n')['possible_duplicates'], 1)))
    test('duplicates endpoint still reports a shared email', lambda: (
        request('POST', '/api/v1/contacts', {'name': 'Eve One', 'email': 'shared@x.test'}, expect=201, opener=import_opener),
        request('POST', '/api/v1/contacts', {'name': 'Eve One Two', 'email': 'SHARED@x.test'}, expect=201, opener=import_opener),
        assert_in('email match', json.dumps(request('GET', '/api/v1/duplicates', opener=import_opener)))))

    def preview_import(filename, data):
        boundary = f'----rolodex-smoke-{time.time_ns()}'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        req = urllib.request.Request(BASE + '/api/v1/import/preview', data=body, method='POST',
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        return json.loads(import_opener.open(req, timeout=10).read().decode())

    def preview_writes_nothing():
        before = len(request('GET', '/api/v1/contacts', opener=import_opener))
        preview = preview_import('p.csv', b'name,email\nPam Quill,pam@x.test\nDan Fox,dan@x.test\n')
        assert_equal(preview['counts']['new'], 1)
        assert_equal(preview['counts']['skipped'], 1)
        assert_equal(len(request('GET', '/api/v1/contacts', opener=import_opener)), before)
    test('import preview reports counts without writing', preview_writes_nothing)
    test('import preview explains why a row is skipped', lambda: assert_in(
        'same email', json.dumps(preview_import('p.csv', b'name,email\nDan Fox,dan@x.test\n')['rows'])))

    def merge_keeps_survivor():
        keep = request('POST', '/api/v1/contacts', {'name': 'Hal Keep', 'phone': '111', 'notes': 'kept note'}, expect=201, opener=import_opener)['contact']
        other = request('POST', '/api/v1/contacts', {'name': 'Hal Keep', 'phone': '222', 'email': 'hal@x.test', 'notes': 'other note'}, expect=201, opener=import_opener)['contact']
        merged = request('POST', '/api/v1/merge', {'primary_id': keep['id'], 'secondary_id': other['id'], 'keep_existing': True}, opener=import_opener)['contact']
        assert_equal(merged['phone'], '111')
        assert_equal(merged['email'], 'hal@x.test')
        assert_in('kept note', merged['notes'])
        assert_in('other note', merged['notes'])
    test('merge with keep_existing keeps the survivor and fills blanks', merge_keeps_survivor)

    # ── 6. Bulk operations ────────────────────────────────────────────
    print('[Bulk Operations]')
    bulk_contact_id = None
    def bulk_tag():
        nonlocal bulk_contact_id
        # First create a contact to tag
        result = request('POST', '/api/v1/contacts', {
            'name': 'Bulk Test Contact',
            'tags': []
        }, expect=201)
        bulk_contact_id = result['contact']['id']
        # Now tag it via bulk
        result = request('POST', '/api/v1/bulk', {
            'action': 'tag',
            'ids': [bulk_contact_id],
            'tag': 'bulk-test'
        })
        assert_equal(result['status'], 'ok')
        assert_equal(result['tagged'], 'bulk-test')
    test('POST /api/v1/bulk tag works', bulk_tag)

    def bulk_delete():
        result = request('POST', '/api/v1/bulk', {'action': 'delete', 'ids': [bulk_contact_id]})
        assert_equal(result['status'], 'ok')
    test('POST /api/v1/bulk delete works', bulk_delete)

    # ── 7. PWA ────────────────────────────────────────────────────────
    print('[PWA]')
    test('GET /sw.js returns service worker', lambda: (
        assert_in('CACHE_NAME', request('GET', '/sw.js', expect=200))
    ))

    # ── Summary ────────────────────────────────────────────────────────
    total = PASS + FAIL
    print(f'\n{"=" * 44}')
    print(f'Results: {PASS}/{total} passed', end='')
    if FAIL:
        print(f', {FAIL} failed ✗')
        sys.exit(1)
    else:
        print(' — all OK ✓')


# ── Assertion helpers ─────────────────────────────────────────────────
def assert_equal(a, b):
    if a != b:
        raise AssertionError(f'{a!r} != {b!r}')

def assert_in(a, b):
    if a not in b:
        raise AssertionError(f'{a!r} not in {b!r}')

def assert_isinstance(obj, cls):
    if not isinstance(obj, cls):
        raise AssertionError(f'expected {cls.__name__}, got {type(obj).__name__}')

def assert_gt(a, b):
    if not (a > b):
        raise AssertionError(f'{a} <= {b}')


if __name__ == '__main__':
    main()
