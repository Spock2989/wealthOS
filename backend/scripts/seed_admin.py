"""
WealthOS — Seed Admin User
Run once on server to create / reset the admin account.

Usage:
  cd /opt/wlthos/backend
  python scripts/seed_admin.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, engine, Base
from models import User
from auth import hash_password

ADMIN_EMAIL    = "tiwarikshitij20@gmail.com"
ADMIN_PASSWORD = "WealthOS2026!"
ADMIN_NAME     = "Kshitij Tiwari"

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if user:
            user.name          = ADMIN_NAME
            user.password_hash = hash_password(ADMIN_PASSWORD)
            user.is_active     = True
            user.is_verified   = True
            user.is_admin      = True
            db.commit()
            print(f"✅ Admin updated: {ADMIN_EMAIL}")
        else:
            user = User(
                email         = ADMIN_EMAIL,
                name          = ADMIN_NAME,
                password_hash = hash_password(ADMIN_PASSWORD),
                is_active     = True,
                is_verified   = True,
                is_admin      = True,
            )
            try:
                user.firm = "WealthOS"
                user.role = "Admin"
            except Exception:
                pass
            db.add(user)
            db.commit()
            print(f"✅ Admin created: {ADMIN_EMAIL}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
