"""
WealthOS — users table schema migration.

The running backend (app/main.py) expects:
  users.hashed_password  (HMAC-SHA256 + pepper)
  users.full_name
  users.firm_name

The original schema (backend/models.py) created:
  users.password_hash    (bcrypt)
  users.name
  users.firm

SQLite's create_all() does not ALTER existing tables, so the new columns are
never added. This script:
  1. Adds missing columns via raw SQL (idempotent — safe to re-run)
  2. Migrates existing rows: copies name→full_name, firm→firm_name
  3. Sets hashed_password for the admin account using the new HMAC scheme

Run on server:
  cd /opt/wlthos/backend
  source venv/bin/activate
  PYTHONPATH=. python3 scripts/migrate_users_schema.py
"""
from __future__ import annotations
import hashlib
import hmac
import os
import sys
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("migrate_users")

# ── Config ────────────────────────────────────────────────────
ADMIN_EMAIL    = "tiwarikshitij20@gmail.com"
ADMIN_PASSWORD = "WealthOS2026!"
ADMIN_FULLNAME = "Kshitij Tiwari"
ADMIN_FIRMNAME = "WealthOS"

# Must match app/api/v1/auth.py
PW_PEPPER = os.getenv("PW_PEPPER", "wealthos-pepper")

DB_PATH = os.getenv(
    "DATABASE_URL",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wealthos.db")
).replace("sqlite:///", "")


def _hmac_hash(password: str) -> str:
    """Exact replica of auth.py's _hash() — must stay in sync."""
    return hmac.new(PW_PEPPER.encode(), password.encode(), hashlib.sha256).hexdigest()


def _col_exists(cursor: sqlite3.Cursor, table: str, col: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cursor.fetchall())


def _row_exists(cursor: sqlite3.Cursor, email: str) -> bool:
    cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower(),))
    return cursor.fetchone() is not None


def migrate(db_path: str) -> None:
    log.info("Connecting to: %s", db_path)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # ── Step 1: add missing columns (idempotent) ──────────────
    columns_to_add = [
        ("hashed_password", "VARCHAR(256)"),
        ("full_name",       "VARCHAR(256)"),
        ("firm_name",       "VARCHAR(256)"),
        ("is_active",       "BOOLEAN DEFAULT 1"),
    ]
    for col, typedef in columns_to_add:
        if not _col_exists(c, "users", col):
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
            log.info("Added column: users.%s", col)
        else:
            log.info("Column already exists: users.%s", col)

    # ── Step 2: copy name→full_name, firm→firm_name for existing rows ──
    if _col_exists(c, "users", "name"):
        c.execute("""
            UPDATE users
            SET full_name = name
            WHERE full_name IS NULL AND name IS NOT NULL
        """)
        updated = c.rowcount
        if updated:
            log.info("Migrated name→full_name for %d rows", updated)

    if _col_exists(c, "users", "firm"):
        c.execute("""
            UPDATE users
            SET firm_name = firm
            WHERE firm_name IS NULL AND firm IS NOT NULL
        """)
        updated = c.rowcount
        if updated:
            log.info("Migrated firm→firm_name for %d rows", updated)

    conn.commit()

    # ── Step 3: upsert admin with correct hashed_password ─────
    new_hash = _hmac_hash(ADMIN_PASSWORD)

    if _row_exists(c, ADMIN_EMAIL):
        c.execute("""
            UPDATE users
            SET hashed_password = ?,
                full_name       = ?,
                firm_name       = ?,
                is_active       = 1
            WHERE email = ?
        """, (new_hash, ADMIN_FULLNAME, ADMIN_FIRMNAME, ADMIN_EMAIL.lower()))
        log.info("Updated admin user: %s", ADMIN_EMAIL)
    else:
        import uuid
        c.execute("""
            INSERT INTO users (id, email, hashed_password, full_name, firm_name, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (str(uuid.uuid4()), ADMIN_EMAIL.lower(), new_hash, ADMIN_FULLNAME, ADMIN_FIRMNAME))
        log.info("Created admin user: %s", ADMIN_EMAIL)

    conn.commit()
    conn.close()

    log.info("Migration complete. Test login:")
    log.info("  POST https://api.wlthos.in/api/v1/auth/login")
    log.info('  {"email": "%s", "password": "%s"}', ADMIN_EMAIL, ADMIN_PASSWORD)


if __name__ == "__main__":
    migrate(DB_PATH)
