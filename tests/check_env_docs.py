#!/usr/bin/env python3
"""Fail when the code reads an environment variable the README's configuration table doesn't list.

Usage:
    python3 tests/check_env_docs.py              # checks README.md
    python3 tests/check_env_docs.py OTHER.md     # checks another copy
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ['app.py', 'gunicorn_config.py', 'migrate_to_postgres.py']
# Set by the platform, never by an operator
PLATFORM_VARS = {'VERCEL'}
# \s* spans newlines: app.py reads ROLODEX_VINTAGE_DIR across two lines
ENV_READ = re.compile(r"os\.environ\.get\(\s*'([A-Z][A-Z0-9_]*)'")


def main():
    readme_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'README.md')
    names = set()
    for name in SOURCES:
        with open(os.path.join(ROOT, name)) as f:
            names |= set(ENV_READ.findall(f.read()))
    with open(readme_path) as f:
        readme = f.read()
    missing = sorted(n for n in names - PLATFORM_VARS if f'`{n}`' not in readme)
    if missing:
        print(f'env docs: {len(missing)} variable(s) read by the code are missing from {readme_path}: '
              f'{", ".join(missing)}. Add a row for each to the configuration table.', file=sys.stderr)
        sys.exit(1)
    print(f'  ✓ README documents all {len(names - PLATFORM_VARS)} env vars the code reads')


if __name__ == '__main__':
    main()
