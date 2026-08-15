"""
DELIBERATELY CLEAN -- for testing Tripwire's false-positive handling.

Every pattern here LOOKS a little like something from vulnerable_example.py
at a glance, but is actually done correctly. If playbook.md's "what NOT to
flag" guidance is working, Tripwire should stay quiet on this file (or at
most raise something low-severity/informational) -- if it flags heavily
here, that's a sign the playbook needs tuning to reduce false positives.
"""
import os
import hashlib
import bcrypt
import requests


# Secret loaded from environment, not hardcoded -- correct pattern
API_KEY = os.environ["API_KEY"]
DATABASE_URL = os.getenv("DATABASE_URL")


# Parameterized query -- not vulnerable to SQL injection
def get_user(conn, user_id):
    query = "SELECT * FROM users WHERE id = %s"
    return conn.execute(query, (user_id,))


# subprocess with a list of args, no shell=True -- not vulnerable to injection
def run_linter(filename):
    import subprocess
    subprocess.run(["ruff", "check", filename])


# TLS verification left on (default) -- correct
def fetch_data(url):
    return requests.get(url)


# Proper password hashing with bcrypt, not MD5/SHA1
def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


# MD5 used for a non-security purpose (cache key), not for passwords --
# a reasonable reviewer might still flag this as "worth a second look" at
# low severity, but it's a legitimate, common pattern.
def cache_key(payload: str) -> str:
    return hashlib.md5(payload.encode()).hexdigest()


# Obviously fake placeholder value in what looks like example/config code --
# should NOT be flagged as a real secret
EXAMPLE_API_KEY = "your-api-key-here"