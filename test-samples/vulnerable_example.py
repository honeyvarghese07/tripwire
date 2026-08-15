"""
DELIBERATELY VULNERABLE -- for testing Tripwire only. Do not use any of
this code for anything real. Each function below is a textbook example of
one category from playbook.md, left uncommented on purpose so you can see
whether Tripwire catches it without being told exactly what to look for.

To test: open a PR that adds this file to your repo and watch the
Tripwire workflow run against it.
"""
import os
import pickle
import subprocess
import hashlib
import requests


# --- Hardcoded secret ---
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
STRIPE_SECRET_KEY = "sk_live_FAKE_DO_NOT_USE_THIS_IS_A_TEST_FIXTURE_ONLY"


# --- SQL injection via string formatting ---
def get_user(conn, user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return conn.execute(query)


# --- Command injection ---
def backup_file(filename):
    os.system(f"cp {filename} /backups/")


def run_user_script(script_name):
    subprocess.run(f"python {script_name}", shell=True)


# --- eval() on external input ---
def calculate(expression):
    return eval(expression)


# --- Insecure deserialization ---
def load_session(raw_bytes):
    return pickle.loads(raw_bytes)


# --- Disabled TLS verification ---
def fetch_data(url):
    return requests.get(url, verify=False)


# --- Weak hashing for passwords ---
def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


# --- Debug mode left on ---
DEBUG = True
SECRET_KEY = "django-insecure-hardcoded-key-do-not-use"