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
    test('duplicate signup returns 409', lambda: request('POST', '/api/v1/auth/signup', {'email': f'smoke-{run_id}@example.test', 'password': 'correct-horse-battery'}, expect=409, opener=anon))
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
