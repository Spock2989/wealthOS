"""
WealthOS — DB Reset + Seed Script
Run ONCE on server after v2.0 migration to drop old schema and create new one.

Usage (from /opt/wlthos/backend/):
    python3 scripts/reset_and_seed.py

What it does:
  1. Backs up the old wealthos.db to wealthos.db.pre_v2
  2. Drops all tables (old schema)
  3. Re-creates tables from app/models/ (new schema)
  4. Seeds the admin user: tiwarikshitij20@gmail.com / WealthOS2026!

Safe to run multiple times — each run resets everything.
"""

import os
import sys
import shutil
import hashlib
import hmac
import uuid
from datetime import datetime

# Ensure backend/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///./wealthos.db")

# ── Import models (must happen before create_tables so metadata is populated)
from app.models.user import User                          # noqa
from app.models.client import Client                      # noqa
from app.models.portfolio import Portfolio                # noqa
from app.models.holding import Holding                    # noqa
from app.models.analytics_snapshot import AnalyticsSnapshot  # noqa
from app.models.ai_report import AIReport                 # noqa
from app.database import Base, engine, SessionLocal, create_tables

# ── STEP 1: Back up old DB
DB_PATH = "wealthos.db"
BACKUP_PATH = "wealthos.db.pre_v2"

if os.path.exists(DB_PATH):
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"✅ Backed up old DB → {BACKUP_PATH}")
else:
    print("ℹ️  No existing DB found — fresh start")

# ── STEP 2: Drop all tables and recreate
print("🔄 Dropping all tables...")
Base.metadata.drop_all(bind=engine)

print("🔄 Creating new schema from app/models/...")
create_tables()
print("✅ Schema created")

# ── STEP 3: Seed admin user
PW_PEPPER = os.getenv("PW_PEPPER", "wealthos-pepper")
ADMIN_EMAIL = "tiwarikshitij20@gmail.com"
ADMIN_PASSWORD = "WealthOS2026!"
ADMIN_NAME = "Kshitij Tiwari"
ADMIN_FIRM = "WealthOS"


def _hash_password(password: str) -> str:
    return hmac.new(PW_PEPPER.encode(), password.encode(), hashlib.sha256).hexdigest()


db = SessionLocal()
try:
    existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing:
        print(f"ℹ️  Admin user already exists: {ADMIN_EMAIL}")
    else:
        admin = User(
            id=str(uuid.uuid4()),
            email=ADMIN_EMAIL,
            hashed_password=_hash_password(ADMIN_PASSWORD),
            full_name=ADMIN_NAME,
            firm_name=ADMIN_FIRM,
            role="admin",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin user seeded: {ADMIN_EMAIL}")
finally:
    db.close()

print("\n🚀 Migration complete. Restart the service:")
print("   systemctl restart wealthos")
print(f"\n🔑 Admin credentials:")
print(f"   Email:    {ADMIN_EMAIL}")
print(f"   Password: {ADMIN_PASSWORD}")
